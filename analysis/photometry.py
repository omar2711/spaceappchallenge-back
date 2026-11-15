"""Forced aperture photometry of the target on every cached exposure (data/raw/<id>/).

One row per exposure: time, detector, wavelength at the target pixel (WCS-WAVE), flux (mJy), error, flag.
Cached in data/analysis/<id>/photometry.ecsv; reused by light curves (T2) and spectra (T3).

Background handling matches B1 (ZODI + sky plane). Saturated holes (NaN cores) are filled with B1's
rim-maximum rule so the flux is a LOWER LIMIT, flagged "saturated".
"""
import logging
import warnings
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from astropy.table import Table
from astropy.time import Time
from astropy.utils.exceptions import AstropyWarning
from astropy.wcs import WCS, FITSFixedWarning
from photutils.aperture import ApertureStats, CircularAnnulus, CircularAperture, aperture_photometry

from pipeline.stack import CONTAM_BITS, REJECT_BITS, SATURATION_BITS, bits, fill_from_rim_max, fit_sky_plane
from pipeline.targets import target_spec

log = logging.getLogger("analysis.photometry")
warnings.simplefilter("ignore", FITSFixedWarning)
warnings.simplefilter("ignore", AstropyWarning)

CACHE_ROOT = Path("data/analysis")
APER_R, ANN_IN, ANN_OUT = 2.0, 5.0, 8.0   # px (6.15"/px): 12" aperture, 31-49" annulus
MAX_BAD_FRACTION = 0.2                     # masked/contaminated pixels allowed inside the aperture
# Detectors where a target is blended with something else (from B1, docs/pipeline_fase5.md).
BLENDED = {"wise0855": {1, 2, 3, 4, 5}}


def measure_exposure(path, coord):
    with fits.open(path) as h:
        hdr = h["IMAGE"].header
        img = h["IMAGE"].data.astype(float)
        var = h["VARIANCE"].data.astype(float)
        flg = h["FLAGS"].data.astype(np.int64)
        zodi = h["ZODI"].data.astype(float)
        wcs = WCS(hdr)
        x, y = (float(v) for v in wcs.world_to_pixel(coord))
        swcs = WCS(hdr, fobj=h, key="W")
        swcs.sip = None
        wl, bw = swcs.pixel_to_world(x, y)
    ny, nx = img.shape
    if not (ANN_OUT <= x < nx - ANN_OUT and ANN_OUT <= y < ny - ANN_OUT):
        return None
    bad = ((flg & bits(REJECT_BITS)) != 0) | ~np.isfinite(img)
    hole = ~np.isfinite(img) & ((flg & bits(SATURATION_BITS)) != 0) & ((flg & bits(REJECT_BITS)) == 0)
    sci = img - zodi
    sci -= fit_sky_plane(sci, ~bad)
    sci[bad & ~hole] = np.nan
    if hole.any():
        sci = fill_from_rim_max(sci, hole)
    good_var = np.isfinite(var) & (var > 0)
    var = np.where(good_var, var, np.nanmax(var[good_var]))

    ap = CircularAperture((x, y), r=APER_R)
    ann = CircularAnnulus((x, y), r_in=ANN_IN, r_out=ANN_OUT)
    bkg = ApertureStats(sci, ann, mask=~np.isfinite(sci), sigma_clip=None)
    _, bkg_med, bkg_std = sigma_clipped_stats(ann.to_mask("center").get_values(sci), sigma=3)
    mask = ~np.isfinite(sci)
    phot = aperture_photometry(sci, ap, error=np.sqrt(var), mask=mask)
    ap_mask = ap.to_mask("exact")
    w = ap_mask.to_image(sci.shape)
    n_bad = float(np.sum(w * (mask | (((flg & bits(CONTAM_BITS)) != 0)))) / ap.area)
    n_holes = int(np.sum((w > 0) & hole))

    pix_sr = float(wcs.proj_plane_pixel_area().to(u.sr).value)
    to_mjy = 1e9 * pix_sr  # MJy/sr summed over pixels -> mJy
    flux = (float(phot["aperture_sum"][0]) - bkg_med * ap.area) * to_mjy
    err = float(np.hypot(phot["aperture_sum_err"][0], bkg_std * ap.area / np.sqrt(max(bkg.sum_aper_area.value, 1)))) * to_mjy
    flag = "saturated" if n_holes else ("contaminated" if n_bad > MAX_BAD_FRACTION else "ok")
    return {"x": x, "y": y, "wavelength_um": float(wl.to(u.um).value), "bandwidth_um": float(bw.to(u.um).value),
            "flux": flux, "err": err, "flag": flag, "n_holes": n_holes, "bad_fraction": n_bad}


def exposure_photometry(target_id, refresh=False):
    """Photometry table for all cached exposures of a named target (cached on disk)."""
    return spec_photometry(target_spec(target_id), CACHE_ROOT / target_id / "photometry.ecsv", refresh,
                           blended=BLENDED.get(target_id, set()))


def spec_photometry(spec, cache, refresh=False, blended=frozenset()):
    """Forced photometry at spec.position_at(t) on every cutout in spec.raw_dir (named target or custom)."""
    target_id = spec.id
    if cache.exists() and not refresh:
        return Table.read(cache)
    raw = spec.raw_dir
    images = Table.read(raw / "images.ecsv")
    rows = []
    for i, r in enumerate(images):
        path = raw / r["file"]
        if not path.exists():
            continue
        mjd = (float(r["t_min"]) + float(r["t_max"])) / 2
        c = spec.position_at(Time(mjd, format="mjd"))
        try:
            m = measure_exposure(path, c)
        except Exception as exc:
            log.warning("%s: %s", r["file"], exc)
            continue
        if m is None:
            continue
        det = int(r["detector"])
        if det in blended and m["flag"] == "ok":
            m["flag"] = "blended"
        rows.append({"obs_id": str(r["obs_id"]), "epoch": str(r["epoch"]), "detector": det, "mjd": mjd, **m})
        if (i + 1) % 100 == 0:
            log.info("%s: %d/%d exposures measured", target_id, i + 1, len(images))
    t = Table(rows=rows)
    t.sort(["detector", "mjd"])
    cache.parent.mkdir(parents=True, exist_ok=True)
    t.write(cache, overwrite=True)
    log.info("%s: %d exposures -> %s (flags: %s)", target_id, len(t), cache,
             dict(zip(*np.unique(t["flag"], return_counts=True))))
    return t
