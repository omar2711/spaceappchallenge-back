"""Offline-only CLI for packaging, integrity verification and B3 demonstration."""

import argparse
import json
from pathlib import Path

from .offline_bundle import export_bundle, validate_bundle
from .service import ScienceService
from .targets import TARGET_NAMES


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    package = commands.add_parser("package", help="Build an allowlisted portable package")
    package.add_argument("--source", type=Path, required=True)
    package.add_argument("--cache", type=Path, required=True)
    package.add_argument("--splices", type=Path, required=True)
    package.add_argument("--output", type=Path, required=True)
    package.add_argument("--fits-mode", choices=["link", "external"], default="link")
    for name in ("validate", "demo"):
        p = commands.add_parser(name)
        p.add_argument("--bundle", type=Path, required=True)
        p.add_argument("--data-root", type=Path, help="Only for an external-data package")
        if name == "demo":
            p.add_argument("--summary", type=Path, required=True, help="NEW JSON output for B3")
            p.add_argument("--recompute", type=Path, help="NEW directory for offline recalculation")
    args = parser.parse_args()
    try:
        if args.command == "package":
            manifest = export_bundle(args.source, args.cache, args.splices, args.output, fits_mode=args.fits_mode)
            print(json.dumps({"success": True, "files": len(manifest.files), "fits_mode": manifest.fits_mode}))
            return 0
        report = validate_bundle(args.bundle, data_root=args.data_root)
        if args.command == "validate" or not report.valid:
            print(report.model_dump_json(indent=2))
            return 0 if report.valid else 1
        if args.summary.exists():
            raise FileExistsError("Choose a fresh summary path")
        service = ScienceService(args.bundle, data_root=args.data_root)
        summary = service.summary()
        summary.success = ({t.target_id for t in summary.targets} == set(TARGET_NAMES)
                           and summary.catalog.availability == "available")
        payload = summary.model_dump(mode="json")
        if args.recompute:
            replay = service.reproduce(args.recompute)
            payload["reproduction"] = replay.model_dump()
            summary.success &= replay.success and replay.targets_reprocessed == 5
            payload["success"] = summary.success
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        with args.summary.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        print(json.dumps({"success": summary.success, "targets": len(summary.targets),
                          "catalog_rows": summary.catalog_rows,
                          "preliminary_photometry_targets": sum(t.photometry.availability == "preliminary" for t in summary.targets),
                          "note": "Integration success does not imply completed spectra, curves or detections"}))
        return 0 if summary.success else 1
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"success": False, "error": type(exc).__name__,
                          "message": "Offline operation failed; inspect integrity and choose fresh output paths"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
