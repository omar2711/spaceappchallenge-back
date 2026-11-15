"""Build public-data/targets/<id>/analysis.json (+ analysis/*.webp) for one or all targets.

    .venv/Scripts/python -m analysis.build --target barnard
    .venv/Scripts/python -m analysis.build --all
"""
import argparse
import json
import logging
from datetime import datetime, timezone

import jsonschema

from analysis.common import PUBLIC_ROOT, SCHEMA_PATH, load_manifest, target_ids
from analysis.diff import build_differences
from analysis.lightcurve import light_curves
from analysis.photometry import exposure_photometry
from analysis.spectra import REFERENCE_BANDS, spectra_from_photometry

log = logging.getLogger("analysis.build")

NOTES = (
    "B2 analysis on top of B1's stacks (data/processed) and cached exposures (data/raw). "
    "Difference images: k*B - A on B1's common grid; colour range shared per detector (blue = fainter/old "
    "position, red = brighter/new position). Their target residual is NOT a variability measurement: each "
    "epoch samples different wavelengths inside a detector (see caveats). Light curves: forced aperture "
    "photometry (r = 2 px) on every exposure, corrected for the spectral shape inside each detector; "
    "fluxes in mJy; variability significance uses a 3% systematic floor. Flags: saturated = core lost, flux "
    "is a lower limit; contaminated = >20% of the aperture masked or flagged; blended = another source in "
    "the aperture. Spectra: one point per exposure at the wavelength its LVF pixel sees, binned at native "
    "resolution (per epoch + combined); band_measurements give Burgasser-style ratio indices and absorption "
    "depths with their significance; reference_bands are plot markers, not detections."
)


def build(target_id, refresh_photometry=False):
    m = load_manifest(target_id)
    t1 = build_differences(target_id)
    phot = exposure_photometry(target_id, refresh=refresh_photometry)
    ranges = {d["id"]: d["wavelength_um"] for d in m["detectors"]}
    curves = light_curves(phot, ranges)
    variable = any(c["variability"]["significant"] for c in curves)
    spectra = spectra_from_photometry(
        phot, kind=m["kind"],
        combine_note=("Combines epochs of a variable target: use the per-epoch spectra for shapes."
                      if variable else None))
    out = {
        "target_id": target_id,
        "difference_images": t1["difference_images"],
        "deep_images": t1["deep_images"],
        "light_curves": curves,
        "spectra": spectra,
        "reference_bands": REFERENCE_BANDS,
        "notes": NOTES,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    jsonschema.validate(out, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    for item in out["difference_images"] + out["deep_images"]:
        assert (PUBLIC_ROOT / target_id / item["file"]).exists(), item["file"]
    path = PUBLIC_ROOT / target_id / "analysis.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    sig = [c["detector"] for c in curves if c["variability"]["significant"]]
    log.info("== %s: %d diffs, %d deep, %d light curves (variable in D%s) -> %s", target_id,
             len(out["difference_images"]), len(out["deep_images"]), len(curves), sig or "-", path)
    return out


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("astropy").setLevel(logging.ERROR)
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--target")
    g.add_argument("--all", action="store_true")
    p.add_argument("--refresh-photometry", action="store_true", help="re-measure cached exposures")
    a = p.parse_args()
    failed = []
    for tid in (target_ids() if a.all else [a.target]):
        try:
            build(tid, a.refresh_photometry)
        except Exception:
            log.exception("== %s FAILED", tid)
            failed.append(tid)
    if failed:
        raise SystemExit(f"failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
