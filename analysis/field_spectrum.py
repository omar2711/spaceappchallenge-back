"""T5: spectrum of ANY position inside an already computed field, from cached cutouts only (no downloads).

API-facing:
    from analysis.field_spectrum import spectrum_in_field, list_fields, FieldNotFound
    spectrum_in_field("m42", ra=83.8088, dec=-5.3730, label="BN/KL")   # ~1 s once the field is prepared

Fields: the named targets (barnard, eps_ind_b, ...) and the demo presets (hl_tau, trapezium, m42 or their
job ids), plus any custom job whose cutouts are still cached.

Speed: building the spatial and wavelength WCS of every exposure costs ~0.1 s each (60 % of the time), so
prepare_field() does it once per field and stores, per exposure, the background-subtracted image, variance,
masks, a per-pixel wavelength map and a linear sky->pixel transform fitted over the field (residual checked).
Queries then only do aperture photometry. Prepared data: data/analysis/fields/<field>/.

CLI:  python -m analysis.field_spectrum --prepare-all
      python -m analysis.field_spectrum --field m42 --ra 83.8088 --dec -5.3730
"""
import argparse
import json
import logging
import threading
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.table import Table
from astropy.utils.exceptions import AstropyWarning
from astropy.wcs import WCS, FITSFixedWarning
from photutils.aperture import CircularAnnulus, CircularAperture, aperture_photometry

from analysis.common import target_ids
from analysis.custom_spectrum import target_px_in_field
from analysis.photometry import ANN_IN, ANN_OUT, APER_R, MAX_BAD_FRACTION
from analysis.spectra import REFERENCE_BANDS, spectra_from_photometry
from pipeline.stack import CONTAM_BITS, REJECT_BITS, SATURATION_BITS, bits, fill_from_rim_max, fit_sky_plane
from pipeline.targets import PUBLIC_ROOT, custom_spec, target_spec

log = logging.getLogger("analysis.field_spectrum")
warnings.simplefilter("ignore", FITSFixedWarning)
warnings.simplefilter("ignore", AstropyWarning)

FIELDS_ROOT = Path("data/analysis/fields")
PRESETS_PATH = PUBLIC_ROOT / "custom" / "presets.json"
JOBS_DIR = Path("data/jobs")
MAX_AFFINE_RESID_PX = 0.05
LAZY_PREPARE_MAX_EXPOSURES = 80   # custom fields this small are prepared on the first query (~10 s)

_CACHE = {}
_LOCK = threading.Lock()


class FieldNotFound(LookupError):
    pass


class FieldNotPrepared(RuntimeError):
    pass


# ------------------------------------------------------------------ field resolution

def _presets():
    if PRESETS_PATH.exists():
        return json.loads(PRESETS_PATH.read_text(encoding="utf-8"))["presets"]
    return []


def resolve_field(field):
    """(canonical field id, Spec, manifest path) for a named target, a preset id/job id or a custom job id."""
    if field in target_ids():
        return field, target_spec(field), PUBLIC_ROOT / "targets" / field / "manifest.json"
    for p in _presets():
        if field in (p["id"], p["job_id"]):
            spec = custom_spec(p["ra"], p["dec"], p["fov_arcmin"], p["max_exposures_per_group"])
            return p["id"], spec, PUBLIC_ROOT / p["manifest"]
    job = JOBS_DIR / f"{field}.json"
    if job.exists():
        j = json.loads(job.read_text(encoding="utf-8"))
        spec = custom_spec(j["ra"], j["dec"], j["fov_arcmin"], j["max_exposures_per_group"])
        if (spec.public_dir / "manifest.json").exists():
            return field, spec, spec.public_dir / "manifest.json"
    raise FieldNotFound(f"unknown field '{field}'")


def list_fields():
    out = [{"field": t, "kind": "target"} for t in target_ids()]
    out += [{"field": p["id"], "kind": "preset", "job_id": p["job_id"]} for p in _presets()]
    for o in out:
        o["prepared"] = (FIELDS_ROOT / o["field"] / "exposures.ecsv").exists()
    return out


# ------------------------------------------------------------------ preparation (slow, once per field)

def _tangent_offsets(ra, dec, ra0, dec0):
    """Offsets (arcsec) on the sky around (ra0, dec0): xi east, eta north (small-field approximation)."""
    dra = (np.asarray(ra) - ra0 + 180) % 360 - 180
    return dra * np.cos(np.radians(dec0)) * 3600, (np.asarray(dec) - dec0) * 3600


def prepare_field(field):
    fid, spec, manifest_path = resolve_field(field)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw = spec.raw_dir
    images = Table.read(raw / "images.ecsv")
    images = images[[(raw / f).exists() for f in images["file"]]]
    if len(images) == 0:
        raise FieldNotPrepared(f"no cached cutouts for field '{fid}' in {raw}")
    ra0, dec0 = manifest["grid_wcs"]["CRVAL1"], manifest["grid_wcs"]["CRVAL2"]
    half = manifest["fov_arcmin"] * 30 + 30  # arcsec: field half-size + 30" margin for the affine fit
    gx, gy = np.meshgrid(np.linspace(-half, half, 7), np.linspace(-half, half, 7))
    g_dec = dec0 + gy.ravel() / 3600
    g_ra = ra0 + gx.ravel() / 3600 / np.cos(np.radians(dec0))
    sky = SkyCoord(g_ra, g_dec, unit="deg")
    out_dir = FIELDS_ROOT / fid
    out_dir.mkdir(parents=True, exist_ok=True)
    arrays, rows = {}, []
    t0 = time.time()
    for i, r in enumerate(images):
        with fits.open(raw / r["file"]) as h:
            hdr = h["IMAGE"].header
            img = h["IMAGE"].data.astype(float)
            var = h["VARIANCE"].data.astype(float)
            flg = h["FLAGS"].data.astype(np.int64)
            zodi = h["ZODI"].data.astype(float)
            wcs = WCS(hdr)
            swcs = WCS(hdr, fobj=h, key="W")
            swcs.sip = None
            ny, nx = img.shape
            yy, xx = np.mgrid[0:ny, 0:nx]
            lam = swcs.pixel_to_world(xx, yy)[0].to(u.um).value.astype(np.float32)
        px, py = wcs.world_to_pixel(sky)
        A = np.column_stack([np.ones(gx.size), gx.ravel(), gy.ravel()])
        cx, *_ = np.linalg.lstsq(A, px, rcond=None)
        cy, *_ = np.linalg.lstsq(A, py, rcond=None)
        resid = float(np.max(np.hypot(A @ cx - px, A @ cy - py)))
        bad = ((flg & bits(REJECT_BITS)) != 0) | ~np.isfinite(img)
        hole = ~np.isfinite(img) & ((flg & bits(SATURATION_BITS)) != 0) & ((flg & bits(REJECT_BITS)) == 0)
        sci = img - zodi
        sci -= fit_sky_plane(sci, ~bad)
        sci[bad & ~hole] = np.nan
        if hole.any():
            sci = fill_from_rim_max(sci, hole)
        good_var = np.isfinite(var) & (var > 0)
        var = np.where(good_var, var, np.nanmax(var[good_var]))
        arrays[f"sci_{i}"] = sci.astype(np.float32)
        arrays[f"var_{i}"] = var.astype(np.float32)
        arrays[f"hole_{i}"] = hole
        arrays[f"contam_{i}"] = (flg & bits(CONTAM_BITS)) != 0
        arrays[f"lam_{i}"] = lam
        rows.append({"i": i, "obs_id": str(r["obs_id"]), "epoch": str(r["epoch"]), "detector": int(r["detector"]),
                     "mjd": (float(r["t_min"]) + float(r["t_max"])) / 2,
                     "pix_sr": float(wcs.proj_plane_pixel_area().to(u.sr).value),
                     "cx0": cx[0], "cx1": cx[1], "cx2": cx[2], "cy0": cy[0], "cy1": cy[1], "cy2": cy[2],
                     "affine_resid_px": resid, "ny": ny, "nx": nx})
    meta = Table(rows=rows)
    meta.meta.update({"field": fid, "ra0": ra0, "dec0": dec0, "prepared_at": datetime.now(timezone.utc).isoformat()})
    np.savez(out_dir / "exposures.npz", **arrays)
    meta.write(out_dir / "exposures.ecsv", overwrite=True)
    worst = float(np.max(meta["affine_resid_px"]))
    log.info("%s: prepared %d exposures in %.1f s (max affine residual %.3f px) -> %s",
             fid, len(meta), time.time() - t0, worst, out_dir)
    if worst > MAX_AFFINE_RESID_PX:
        log.warning("%s: affine residual %.3f px exceeds %.2f px", fid, worst, MAX_AFFINE_RESID_PX)
    with _LOCK:
        _CACHE.pop(fid, None)
    return meta


def _load(fid, spec):
    with _LOCK:
        if fid in _CACHE:
            return _CACHE[fid]
    d = FIELDS_ROOT / fid
    if not (d / "exposures.ecsv").exists():
        n = len(Table.read(spec.raw_dir / "images.ecsv")) if (spec.raw_dir / "images.ecsv").exists() else 0
        cached = sum(1 for _ in spec.raw_dir.glob("*.fits")) if spec.raw_dir.exists() else 0
        if 0 < cached <= LAZY_PREPARE_MAX_EXPOSURES:
            prepare_field(fid)
        else:
            raise FieldNotPrepared(f"field '{fid}' is not prepared ({cached}/{n} cutouts cached); "
                                   f"run python -m analysis.field_spectrum --prepare {fid}")
    meta = Table.read(d / "exposures.ecsv")
    data = np.load(d / "exposures.npz")
    arrays = {k: data[k] for k in data.files}  # small (a few MB per field): keep in memory for speed
    with _LOCK:
        _CACHE[fid] = (meta, arrays)
    return meta, arrays


# ------------------------------------------------------------------ query (fast)

def _measure(sci, var, hole, contam, lam, x, y, pix_sr):
    ny, nx = sci.shape
    if not (ANN_OUT <= x < nx - ANN_OUT and ANN_OUT <= y < ny - ANN_OUT):
        return None
    ap = CircularAperture((x, y), r=APER_R)
    ann = CircularAnnulus((x, y), r_in=ANN_IN, r_out=ANN_OUT)
    ann_vals = ann.to_mask(method="center").get_values(sci)
    ann_vals = ann_vals[np.isfinite(ann_vals)]
    med = np.median(ann_vals)
    mad = 1.4826 * np.median(np.abs(ann_vals - med))
    keep = np.abs(ann_vals - med) < 3 * mad if mad > 0 else np.ones(ann_vals.size, bool)
    bkg_med, bkg_std, n_ann = float(np.median(ann_vals[keep])), float(np.std(ann_vals[keep])), int(keep.sum())
    mask = ~np.isfinite(sci)
    phot = aperture_photometry(sci, ap, error=np.sqrt(var), mask=mask)
    w = ap.to_mask(method="exact").to_image(sci.shape)
    bad_frac = float(np.sum(w * (mask | contam)) / ap.area)
    n_holes = int(np.sum((w > 0) & hole))
    to_mjy = 1e9 * pix_sr
    flux = (float(phot["aperture_sum"][0]) - bkg_med * ap.area) * to_mjy
    err = float(np.hypot(phot["aperture_sum_err"][0], bkg_std * ap.area / np.sqrt(max(n_ann, 1)))) * to_mjy
    xi, yi = int(np.clip(round(x), 0, nx - 1)), int(np.clip(round(y), 0, ny - 1))
    flag = "saturated" if n_holes else ("contaminated" if bad_frac > MAX_BAD_FRACTION else "ok")
    return {"wavelength_um": float(lam[yi, xi]), "flux": flux, "err": err, "flag": flag, "n_holes": n_holes,
            "bad_fraction": bad_frac, "x": float(x), "y": float(y)}


def spectrum_in_field(field, ra, dec, label=None):
    """Spectrum at (ra, dec) inside a prepared field, from cached cutouts only. Returns a JSON-ready dict.
    Raises FieldNotFound, FieldNotPrepared, or ValueError (position outside the field / no usable exposure)."""
    t0 = time.time()
    ra, dec = float(ra) % 360, float(dec)
    fid, spec, manifest_path = resolve_field(field)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tpx = target_px_in_field(manifest, ra, dec)
    nx, ny = manifest["image_size_px"]
    if not (0 <= tpx[0] <= nx - 1 and 0 <= tpx[1] <= ny - 1):
        raise ValueError(f"position is outside field '{fid}' ({manifest['fov_arcmin']}' wide)")
    meta, arrays = _load(fid, spec)
    xi, eta = _tangent_offsets(ra, dec, meta.meta["ra0"], meta.meta["dec0"])
    rows = []
    for r in meta:
        i = int(r["i"])
        x = r["cx0"] + r["cx1"] * xi + r["cx2"] * eta
        y = r["cy0"] + r["cy1"] * xi + r["cy2"] * eta
        m = _measure(arrays[f"sci_{i}"], arrays[f"var_{i}"], arrays[f"hole_{i}"], arrays[f"contam_{i}"],
                     arrays[f"lam_{i}"], float(x), float(y), float(r["pix_sr"]))
        if m:
            rows.append({"obs_id": r["obs_id"], "epoch": r["epoch"], "detector": int(r["detector"]),
                         "mjd": float(r["mjd"]), **m})
    if not rows:
        raise ValueError("no usable exposure at this position (too close to the cutout edges?)")
    phot = Table(rows=rows)
    position = {"ra_deg": round(ra, 6), "dec_deg": round(dec, 6), "target_px": tpx}
    if label:
        position["label"] = label
    spectra = spectra_from_photometry(phot, label=label, position=position, kind="custom")
    flags = dict(zip(*np.unique(np.asarray(phot["flag"]), return_counts=True)))
    return {
        "field": fid, "ra": round(ra, 6), "dec": round(dec, 6), "label": label, "target_px": tpx,
        "n_exposures": len(rows), "flags": {str(k): int(v) for k, v in flags.items()},
        "spectra": spectra, "reference_bands": REFERENCE_BANDS,
        "notes": ("Forced aperture photometry (r = 12\") on cached exposures of the field at a fixed sky position "
                  "(no proper motion). One point per exposure; saturated points are lower limits."),
        "elapsed_s": round(time.time() - t0, 2),
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("astropy").setLevel(logging.ERROR)
    p = argparse.ArgumentParser()
    p.add_argument("--prepare", nargs="*", help="prepare these fields")
    p.add_argument("--prepare-all", action="store_true")
    p.add_argument("--field")
    p.add_argument("--ra", type=float)
    p.add_argument("--dec", type=float)
    a = p.parse_args()
    if a.prepare_all:
        for f in list_fields():
            try:
                prepare_field(f["field"])
            except Exception as exc:
                log.warning("%s: %s", f["field"], exc)
    for f in a.prepare or []:
        prepare_field(f)
    if a.field:
        res = spectrum_in_field(a.field, a.ra, a.dec)
        c = res["spectra"][-1]
        log.info("%s at (%.5f, %.5f): %d exposures %s, %d bins, %.2f s", res["field"], res["ra"], res["dec"],
                 res["n_exposures"], res["flags"], len(c["points"]), res["elapsed_s"])


if __name__ == "__main__":
    main()
