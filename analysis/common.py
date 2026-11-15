"""Shared helpers for analysis/: paths, B1 products (read-only), image writers."""
import json
import re
from pathlib import Path

import numpy as np
from astropy.io import fits
from PIL import Image

PUBLIC_ROOT = Path("public-data/targets")
PROCESSED_ROOT = Path("data/processed")
RAW_ROOT = Path("data/raw")
SCHEMA_PATH = Path(__file__).with_name("analysis.schema.json")


def load_manifest(target_id):
    return json.loads((PUBLIC_ROOT / target_id / "manifest.json").read_text(encoding="utf-8"))


def target_ids():
    index = json.loads((PUBLIC_ROOT / "index.json").read_text(encoding="utf-8"))
    return [t["target_id"] for t in index["targets"]]


def epoch_key(e):
    return int(re.sub(r"\D", "", e) or 0)


def load_stack(target_id, epoch, detector):
    """One B1 stack (data/processed/<id>/<epoch>_D<det>.fits) as plain arrays + header. None if missing."""
    path = PROCESSED_ROOT / target_id / f"{epoch}_D{detector}.fits"
    if not path.exists():
        return None
    with fits.open(path) as h:
        return {
            "image": h["IMAGE"].data.astype(float),
            "var": h["VARIANCE"].data.astype(float),
            "filled": h["FILLED"].data.astype(int),
            "header": h[0].header.copy(),
            "wcs_header": h["IMAGE"].header.copy(),
            "wavelengths_um": np.asarray(h["EXPOSURES"].data["wavelength_um"], dtype=float),
        }


def to_uint8_rows(x):
    """[0,1] float image in FITS orientation (y up) -> uint8 rows for the web (y down), like B1's WebP."""
    return (np.flipud(np.clip(x, 0, 1)) * 255).round().astype(np.uint8)


def save_webp_gray(x01, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(to_uint8_rows(x01), mode="L").save(path, lossless=True)


def diverging_rgb(img, limit):
    """Symmetric diverging map (blue < 0 < red, white = 0) without matplotlib state. img in FITS orientation."""
    import matplotlib

    cmap = matplotlib.colormaps["RdBu_r"]
    x = np.clip((np.nan_to_num(img) / limit + 1) / 2, 0, 1)
    rgb = (cmap(np.flipud(x))[..., :3] * 255).round().astype(np.uint8)
    return rgb


def save_webp_rgb(rgb, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, mode="RGB").save(path, lossless=True)


def fits_to_web_xy(x, y, ny):
    """0-based FITS pixel (y up) -> 0-based web pixel (y down), same convention as manifest target_px."""
    return float(x), float(ny - 1 - y)
