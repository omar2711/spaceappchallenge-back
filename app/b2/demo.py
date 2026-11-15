"""Explicit opt-in live demo: python -m app.b2.demo --help."""

import argparse
import json
from pathlib import Path

import httpx
from astropy.coordinates import SkyCoord
from astropy.utils.data import conf

from .archive import search_observations, utc_now
from .observation_models import ApertureConfig, DownloadLimits, ObservationQuery, ScienceRun, Target
from .pipeline import export_run, reprocess_run, run_target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["RW Aurigae", "R Draconis"], required=True)
    parser.add_argument("--ra", type=float)
    parser.add_argument("--dec", type=float)
    parser.add_argument("--coordinate-source")
    parser.add_argument("--output", type=Path, required=True, help="Fresh directory, not overwritten")
    parser.add_argument("--cache", type=Path, default=Path(".b2-cache"))
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--max-files", type=int, default=2)
    parser.add_argument("--download", action="store_true", help="Opt in to bounded FITS downloads")
    parser.add_argument("--reprocess", type=Path, help="Existing run.json: offline replay, no queries or downloads")
    parser.add_argument("--annulus-outer", type=float, default=8)
    parser.add_argument("--reject-bits", type=int, help="Required for photometry; release-specific bad-pixel bitmask")
    parser.add_argument("--flag-policy-source", help="Documentation or review identifier for this bitmask")
    args = parser.parse_args()
    if (args.ra is None) != (args.dec is None):
        parser.error("Provide both --ra and --dec")
    if args.ra is not None and not args.coordinate_source:
        parser.error("Explicit coordinates require --coordinate-source")
    if (args.download or args.reprocess) and (args.reject_bits is None or not args.flag_policy_source):
        parser.error("Processing requires --reject-bits and --flag-policy-source")
    if args.download and args.reprocess:
        parser.error("Choose download or offline reprocess")
    if args.output.exists():
        parser.error("Output directory exists; choose a fresh path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        if args.reprocess:
            previous = ScienceRun.model_validate_json(args.reprocess.read_text(encoding="utf-8"))
            if previous.target.target_id != args.target:
                parser.error("Replay target does not match --target")
            aperture = ApertureConfig(rejected_flag_bits=args.reject_bits,
                flag_policy_source=args.flag_policy_source, annulus_outer_px=args.annulus_outer)
            run = export_run(reprocess_run(previous, args.cache, aperture), args.output)
            print(json.dumps({"status": run.status, "measurements": len(run.measurements),
                              "output": str(args.output)}))
            return
        if args.ra is None:
            name = "RW Aur" if args.target == "RW Aurigae" else "R Dra"
            with conf.set_temp("remote_timeout", 20):
                coord = SkyCoord.from_name(name)
            ra, dec = float(coord.ra.deg), float(coord.dec.deg)
            source = f"CDS Sesame name resolver: {name}; resolved {utc_now()}"
        else:
            ra, dec, source = args.ra, args.dec, args.coordinate_source
        target = Target(target_id=args.target, ra_deg=ra, dec_deg=dec, coordinate_source=source)
        query = ObservationQuery(ra_deg=ra, dec_deg=dec, radius_deg=1 / 3600, limit=args.limit)
        if not args.download:
            result = search_observations(query)
            args.output.mkdir()
            payload = {"target": target.model_dump(), "search": result.model_dump(mode="json")}
            (args.output / "search.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(json.dumps({"status": result.status, "rows": len(result.observations),
                              "output": str(args.output)}))
        else:
            aperture = ApertureConfig(rejected_flag_bits=args.reject_bits,
                flag_policy_source=args.flag_policy_source, annulus_outer_px=args.annulus_outer)
            with httpx.Client(timeout=30) as client:
                run = run_target(target, query, args.cache, client, aperture,
                                 DownloadLimits(max_files=args.max_files))
            run = export_run(run, args.output)
            print(json.dumps({"status": run.status, "cutouts": len(run.cutouts),
                              "measurements": len(run.measurements), "output": str(args.output)}))
    except Exception as exc:
        args.output.mkdir(exist_ok=True)
        with (args.output / "failure.json").open("x", encoding="utf-8") as handle:
            json.dump({"status": "failed", "attempted_at_utc": utc_now(),
                       "target": args.target, "error": f"{type(exc).__name__}: {exc}"}, handle, indent=2)
        raise


if __name__ == "__main__":
    main()
