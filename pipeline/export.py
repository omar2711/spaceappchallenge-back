"""Phase 3: export stacks as WebP frames + manifest.json for the web.

    .venv/Scripts/python -m pipeline.export --target barnard

Inputs:  data/processed/<target>/<epoch>_D<n>.fits (from pipeline.stack)
Outputs: public-data/targets/<target>/<epoch>_D<n>.webp
         public-data/targets/<target>/manifest.json
         public-data/targets/index.json
"""
import argparse
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from astropy.convolution import Gaussian2DKernel, interpolate_replace_nans
from astropy.io import fits
from astropy.table import Table
from astropy.time import Time
from astropy.visualization import AsinhStretch
from PIL import Image

from pipeline.fetch import COLLECTIONS, RAW_ROOT
from pipeline.stack import PIXEL_SCALE_ARCSEC, PROCESSED_ROOT
from pipeline.targets import get_target

log = logging.getLogger("export")

PUBLIC_ROOT = Path("public-data/targets")
SCHEMA_PATH = Path(__file__).with_name("manifest.schema.json")
STRETCH_A = 0.002         # asinh softening: lower = more contrast in faint parts
PERCENTILES = (2.0, 99.5)  # computed jointly over all epochs of a detector; top 0.5% (bright cores) saturate

# Nominal detector ranges (um), from em_min/em_max in the SIA results (docs/pipeline_fase1.md).
DETECTOR_RANGE_UM = {1: [0.746, 1.117], 2: [1.103, 1.650], 3: [1.630, 2.435],
                     4: [2.403, 3.847], 5: [3.811, 4.430], 6: [4.412, 5.010]}

NOTES = (
    "Each frame is the inverse-variance weighted mean (MJy/sr) of all exposures of one detector in one "
    "survey pass, aligned on grid_wcs. Compare frames of the SAME detector across epochs: each detector "
    "covers a different wavelength range. target_px is in WebP pixel coordinates (0-based, origin top-left, "
    "y down, pixel centres at integers); grid_wcs follows the FITS convention (1-based, y up). "
    "Bright targets saturate: see frames[].saturated_exposures; do not use FILLED pixels for photometry."
)


def epoch_key(e):
    return int(e[1:])


def to_frame(img, lo, hi):
    """NaN-fill, asinh stretch with fixed limits, flip to top-down rows, return uint8."""
    if np.any(~np.isfinite(img)):
        img = interpolate_replace_nans(img, Gaussian2DKernel(1.0))
        img = np.where(np.isfinite(img), img, lo)
    x = np.clip((img - lo) / (hi - lo), 0, 1)
    x = AsinhStretch(a=STRETCH_A)(x)
    return (np.flipud(x) * 255).round().astype(np.uint8)


def export_target(target_id):
    src = PROCESSED_ROOT / target_id
    out = PUBLIC_ROOT / target_id
    out.mkdir(parents=True, exist_ok=True)

    stacks = {}
    for path in sorted(src.glob("S*_D*.fits")):
        m = re.match(r"(S\d+)_D(\d)\.fits", path.name)
        with fits.open(path) as hdul:
            stacks[(m.group(1), int(m.group(2)))] = {
                "path": path, "header": hdul[0].header.copy(), "image": hdul["IMAGE"].data.astype(float),
                "wcs_header": hdul["IMAGE"].header.copy(),
            }
    if not stacks:
        raise SystemExit(f"no stacks in {src}; run pipeline.stack first")
    epochs = sorted({e for e, _ in stacks}, key=epoch_key)
    detectors = sorted({d for _, d in stacks})
    any_stack = next(iter(stacks.values()))
    ny, nx = any_stack["image"].shape

    # One scale per detector shared by all epochs (so the video does not flicker). Median of the per-frame
    # percentiles, so a single bad frame (few exposures, artefacts) cannot wash out the others.
    limits = {}
    for d in detectors:
        per_frame = [np.nanpercentile(s["image"], PERCENTILES) for (e, dd), s in stacks.items() if dd == d]
        lo, hi = np.median(per_frame, axis=0)
        limits[d] = [float(lo), float(hi)]

    det_entries = []
    for d in detectors:
        frames = []
        for e in epochs:
            s = stacks.get((e, d))
            if s is None:
                continue
            h = s["header"]
            name = f"{e}_D{d}.webp"
            Image.fromarray(to_frame(s["image"], *limits[d]), mode="L").save(out / name, lossless=True)
            frames.append({
                "epoch": e, "file": name, "fits": s["path"].name,
                "n_images": int(h["NIMAGES"]),
                "target_px": [round(float(h["TGT_X"]), 3), round(float(ny - 1 - h["TGT_Y"]), 3)],
                "flags_fraction": round(float(h["CONTAM"]), 4),
                "saturated_exposures": int(h["NSATUR"]),
                "wavelength_at_target_um": [round(float(h["WAVEMIN"]), 4), round(float(h["WAVEMAX"]), 4)],
                "date_mid": h["DATE-MID"],
            })
        det_entries.append({"id": d, "wavelength_um": DETECTOR_RANGE_UM[d], "frames": frames})

    epoch_entries = []
    for e in epochs:
        hs = [s["header"] for (ee, _), s in stacks.items() if ee == e]
        beg = min(Time(h["DATE-BEG"]) for h in hs)
        end = max(Time(h["DATE-END"]) for h in hs)
        mid = Time((beg.mjd + end.mjd) / 2, format="mjd")
        epoch_entries.append({"id": e, "date_start": beg.isot[:19], "date_end": end.isot[:19], "date_mid": mid.isot[:19]})

    info = get_target(target_id)
    a = info["astrometry"]
    wh = any_stack["wcs_header"]
    grid_wcs = {k: wh[k] for k in ["CTYPE1", "CTYPE2", "CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2",
                                    "CDELT1", "CDELT2", "CUNIT1", "CUNIT2"] if k in wh}
    grid_wcs.update({"NAXIS1": nx, "NAXIS2": ny})
    n_images = len(Table.read(RAW_ROOT / target_id / "images.ecsv"))

    manifest = {
        "target_id": target_id,
        "name": info["name"],
        "kind": info["kind"],
        "ref_coord": {"ra_deg": round(float(a["ra"]), 7), "dec_deg": round(float(a["dec"]), 7),
                      "epoch": f"J{float(a['epoch']):.1f}", "source": a["source"]},
        "proper_motion_mas_yr": {"pmra": round(float(a["pmra"]), 3), "pmdec": round(float(a["pmdec"]), 3)},
        "fov_arcmin": round(nx * PIXEL_SCALE_ARCSEC / 60, 3),
        "pixel_scale_arcsec": PIXEL_SCALE_ARCSEC,
        "image_size_px": [nx, ny],
        "grid_wcs": grid_wcs,
        "epochs": epoch_entries,
        "detectors": det_entries,
        "stretch": {"method": "asinh", "a": STRETCH_A, "percentiles": list(PERCENTILES),
                    "per_detector_limits": {str(d): [round(v, 4) for v in limits[d]] for d in detectors},
                    "units": "MJy/sr"},
        "source": {"collections": COLLECTIONS, "n_images_available": n_images,
                   "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        "notes": NOTES + (" " + info["notes"] if info.get("notes") else ""),
    }
    validate_manifest(manifest)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("%s: %d frames, manifest -> %s", target_id, sum(len(d["frames"]) for d in det_entries), out / "manifest.json")
    write_index()
    return manifest


def validate_manifest(manifest):
    import jsonschema
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(manifest, schema)
    for d in manifest["detectors"]:
        for f in d["frames"]:
            assert (PUBLIC_ROOT / manifest["target_id"] / f["file"]).exists(), f["file"]


def write_index():
    entries = []
    for mpath in sorted(PUBLIC_ROOT.glob("*/manifest.json")):
        m = json.loads(mpath.read_text(encoding="utf-8"))
        entries.append({"target_id": m["target_id"], "name": m["name"], "kind": m["kind"],
                        "ra_deg": m["ref_coord"]["ra_deg"], "dec_deg": m["ref_coord"]["dec_deg"],
                        "manifest": f"{m['target_id']}/manifest.json",
                        "epochs": [e["id"] for e in m["epochs"]],
                        "detectors": [d["id"] for d in m["detectors"]]})
    index = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "targets": entries}
    (PUBLIC_ROOT / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="barnard")
    export_target(p.parse_args().target)


if __name__ == "__main__":
    main()
