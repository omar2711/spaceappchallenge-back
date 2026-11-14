"""Phase 2: align cutouts on a common TAN grid and combine them per (epoch x detector).

    .venv/Scripts/python -m pipeline.stack --target barnard

Inputs:  data/raw/<target>/images.ecsv + cutouts (from pipeline.fetch)
Outputs: data/processed/<target>/<epoch>_D<n>.fits
"""
import argparse
import logging
import warnings
from datetime import datetime, timezone
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.stats import sigma_clip, sigma_clipped_stats
from astropy.table import Table
from astropy.time import Time
from astropy.utils.exceptions import AstropyWarning
from astropy.wcs import WCS, FITSFixedWarning
from reproject import reproject_interp
from scipy.ndimage import maximum_filter

from pipeline.fetch import RAW_ROOT
from pipeline.targets import get_target, reference_coord

log = logging.getLogger("stack")
warnings.simplefilter("ignore", FITSFixedWarning)
warnings.simplefilter("ignore", AstropyWarning)
logging.getLogger("astropy").setLevel(logging.ERROR)  # silences the SIP/WAVE-TAB notice

PROCESSED_ROOT = Path("data/processed")
PIXEL_SCALE_ARCSEC = 6.15
FOV_ARCMIN = 4.0
CLIP_SIGMA = 5.0

# FLAGS bits (names from MSKNnn in the FLAGS header). Validated on Barnard, see docs/pipeline_fase1.md.
# Bright stars carry TRANSIENT/OVERFLOW/SUR_ERROR/BLOOM on their core, so those are NOT rejected;
# cosmic rays are removed by sigma-clipping across exposures instead.
REJECT_BITS = [6, 9, 10, 11, 17, 19, 25, 27]   # NONFUNC MISSING_DATA HOT COLD PERSIST OUTLIER STREAK SNOWBALL
SATURATION_BITS = [0, 1, 2, 26]                 # TRANSIENT OVERFLOW SUR_ERROR BLOOM (checked on the target)
CONTAM_BITS = [7, 20, 22, 23, 24, 28]           # DICHROIC CROSSTALK GHOST GHOST_FPA GHOST_EXT HALO


def bits(bs):
    return int(sum(1 << b for b in bs))


def make_grid(center, fov_arcmin=FOV_ARCMIN, scale_arcsec=PIXEL_SCALE_ARCSEC):
    """North-up, east-left TAN grid centred on `center`, odd size so the centre is a pixel centre."""
    n = int(round(fov_arcmin * 60 / scale_arcsec))
    n += (n + 1) % 2
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [center.ra.deg, center.dec.deg]
    w.wcs.crpix = [(n + 1) / 2, (n + 1) / 2]
    w.wcs.cdelt = [-scale_arcsec / 3600, scale_arcsec / 3600]
    w.wcs.cunit = ["deg", "deg"]
    return w, (n, n)


def fit_sky_plane(img, good, iters=3, sigma=3.0):
    """Least-squares plane a + b*x + c*y over sky pixels, rejecting sources by iterative sigma-clipping."""
    yy, xx = np.indices(img.shape, dtype=float)
    use = good & np.isfinite(img)
    coef = np.array([np.nanmedian(img[use]), 0.0, 0.0])
    for _ in range(iters):
        if use.sum() < 10:
            break
        A = np.column_stack([np.ones(use.sum()), xx[use], yy[use]])
        coef, *_ = np.linalg.lstsq(A, img[use], rcond=None)
        resid = img - (coef[0] + coef[1] * xx + coef[2] * yy)
        _, med, std = sigma_clipped_stats(resid[use], sigma=sigma)
        use = good & np.isfinite(img) & (np.abs(resid - med) < sigma * std)
    return coef[0] + coef[1] * xx + coef[2] * yy


def fill_from_rim_max(img, hole, max_iter=10):
    out = img.copy()
    todo = hole & ~np.isfinite(out)
    for _ in range(max_iter):
        if not todo.any():
            break
        neigh = maximum_filter(np.where(np.isfinite(out), out, -np.inf), size=3, mode="constant", cval=-np.inf)
        ready = todo & np.isfinite(neigh)
        out[ready] = neigh[ready]
        todo &= ~ready
    return out


def load_exposure(path, coord):
    """Return background-subtracted image, variance, flags and per-exposure metadata."""
    with fits.open(path) as hdul:
        h = hdul["IMAGE"].header
        img = hdul["IMAGE"].data.astype(float)
        var = hdul["VARIANCE"].data.astype(float)
        flg = hdul["FLAGS"].data.astype(np.int64)
        zodi = hdul["ZODI"].data.astype(float)
        wcs = WCS(h)
        x, y = wcs.world_to_pixel(coord)
        swcs = WCS(h, fobj=hdul, key="W")
        swcs.sip = None
        wl, bw = swcs.pixel_to_world(x, y)
        meta = {"detector": int(h["DETECTOR"]), "mjd_avg": float(h["MJD-AVG"]),
                "wavelength_um": float(wl.to(u.um).value), "bandwidth_um": float(bw.to(u.um).value)}
    bad = ((flg & bits(REJECT_BITS)) != 0) | ~np.isfinite(img)
    # Saturated cores keep a valid IMAGE but VARIANCE is NaN/0 there: give them a conservative
    # (low-weight) variance instead of dropping the star.
    no_var = ~bad & (~np.isfinite(var) | (var <= 0))
    if np.any(no_var):
        var[no_var] = np.nanmax(var[~bad & ~no_var])
    meta_nvar = int(no_var.sum())
    sci = img - zodi
    # ZODI is a model; remove the remaining offset and any linear gradient (e.g. scattered light from a
    # bright neighbour) with a plane fitted to sigma-clipped sky pixels.
    sci -= fit_sky_plane(sci, ~bad)
    sci[bad] = np.nan
    var[bad] = np.nan
    # Fully saturated pixels in bright cores come as NaN in IMAGE (flags OVERFLOW/SUR_ERROR/BLOOM).
    # Fill only those from their neighbours so the star is not a hole; the true peak was higher,
    # so these pixels are recorded (FILLED layer) and must not be used for photometry.
    hole = ~np.isfinite(img) & ((flg & bits(SATURATION_BITS)) != 0) & ((flg & bits(REJECT_BITS)) == 0)
    if np.any(hole):
        # A saturated core is brighter than its rim, so fill from the outside in with the neighbourhood
        # maximum (a flat-topped plateau). Averaging the rim instead leaves a dark "donut" on very bright
        # stars such as R Dra, whose holes are up to ~14 px.
        sci = fill_from_rim_max(sci, hole)
        var[hole] = np.nanmax(var)
    meta["n_holes_filled"] = int(np.sum(hole & np.isfinite(sci)))
    xi, yi = int(round(float(x))), int(round(float(y)))
    core = flg[max(yi - 1, 0):yi + 2, max(xi - 1, 0):xi + 2]
    meta["saturated"] = bool(np.any(core & bits(SATURATION_BITS)))
    meta["contam_fraction"] = float(np.mean((flg & bits(CONTAM_BITS)) != 0))
    meta["bad_fraction"] = float(np.mean(bad))
    meta["n_var_filled"] = meta_nvar
    return sci, var, hole.astype(float), wcs, meta


def combine(images, variances):
    """Sigma-clipped inverse-variance weighted mean along axis 0."""
    cube = np.ma.masked_invalid(np.asarray(images))
    if cube.shape[0] >= 3:
        clipped = sigma_clip(cube, sigma=CLIP_SIGMA, axis=0, cenfunc="median", stdfunc="mad_std", masked=True)
    else:
        clipped = cube
    n_clipped = int(np.ma.getmaskarray(clipped).sum() - np.ma.getmaskarray(cube).sum())
    w = np.ma.masked_array(1.0 / np.asarray(variances), mask=np.ma.getmaskarray(clipped) | ~np.isfinite(variances))
    wsum = w.sum(axis=0)
    mean = (clipped * w).sum(axis=0) / wsum
    out_var = 1.0 / wsum
    nimg = (~np.ma.getmaskarray(w)).sum(axis=0)
    return mean.filled(np.nan), np.ma.filled(out_var, np.nan), nimg.astype(np.int16), n_clipped


def stack_target(target_id, fov_arcmin=None):
    raw = RAW_ROOT / target_id
    images = Table.read(raw / "images.ecsv")
    # Grid epoch from the full index, so the grid does not move as more cutouts arrive.
    t_all = Time(np.asarray(images["t_min"], dtype=float), format="mjd")
    images = images[[(raw / f).exists() for f in images["file"]]]
    log.info("%s: %d cutouts available", target_id, len(images))

    c_ref = reference_coord(target_id)
    fov_arcmin = fov_arcmin or get_target(target_id)["fov_arcmin"]
    t_grid = Time(np.mean(t_all.mjd), format="mjd")
    center = c_ref.apply_space_motion(new_obstime=t_grid)
    grid, shape = make_grid(SkyCoord(center.ra, center.dec), fov_arcmin)
    log.info("grid %dx%d centred on RA %.6f Dec %.6f (target at %s)", shape[1], shape[0],
             center.ra.deg, center.dec.deg, t_grid.iso[:10])

    out_dir = PROCESSED_ROOT / target_id
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for epoch in sorted(set(images["epoch"]), key=lambda s: int(s[1:])):
        for det in range(1, 7):
            sel = images[(images["epoch"] == epoch) & (images["detector"] == det)]
            if len(sel) == 0:
                continue
            ims, vrs, holes, rows = [], [], [], []
            for r in sel:
                t_mid = Time((float(r["t_min"]) + float(r["t_max"])) / 2, format="mjd")
                coord = c_ref.apply_space_motion(new_obstime=t_mid)
                try:
                    sci, var, hole, wcs, meta = load_exposure(raw / r["file"], coord)
                except Exception as exc:
                    log.warning("skipping %s: %s", r["file"], exc)
                    continue
                im_r, fp = reproject_interp((sci, wcs), grid, shape_out=shape)
                var_r, _ = reproject_interp((var, wcs), grid, shape_out=shape)
                hole_r, _ = reproject_interp((hole, wcs), grid, shape_out=shape)
                holes.append(np.nan_to_num(hole_r) > 0)
                im_r[fp < 0.99] = np.nan
                ims.append(im_r)
                vrs.append(var_r)
                tx, ty = grid.world_to_pixel(coord)
                rows.append({"obs_id": str(r["obs_id"]), "collection": str(r["obs_collection"]),
                             "mjd_mid": t_mid.mjd, "target_x": float(tx), "target_y": float(ty), **meta})
            if not ims:
                continue
            mean, var, nimg, n_clipped = combine(ims, vrs)
            exp = Table(rows)
            mjd = np.asarray(exp["mjd_mid"])
            t_mid_epoch = Time(np.mean(mjd), format="mjd")
            tpos = c_ref.apply_space_motion(new_obstime=t_mid_epoch)
            tx, ty = grid.world_to_pixel(tpos)

            hdr = grid.to_header()
            hdr["BUNIT"] = "MJy/sr"
            primary = fits.PrimaryHDU()
            ph = primary.header
            ph["TARGET"] = target_id
            ph["EPOCH"] = epoch
            ph["DETECTOR"] = det
            ph["NIMAGES"] = (len(ims), "exposures combined")
            ph["NCLIPPED"] = (n_clipped, "pixels rejected by sigma-clipping")
            ph["DATE-BEG"] = Time(mjd.min(), format="mjd").isot
            ph["DATE-END"] = Time(mjd.max(), format="mjd").isot
            ph["DATE-MID"] = t_mid_epoch.isot
            ph["WAVEMIN"] = (float(np.min(exp["wavelength_um"])), "um, at target, over exposures")
            ph["WAVEMAX"] = (float(np.max(exp["wavelength_um"])), "um, at target, over exposures")
            ph["TGT_X"] = (float(tx), "0-based pixel of target at DATE-MID")
            ph["TGT_Y"] = (float(ty), "0-based pixel of target at DATE-MID")
            ph["TGT_RA"] = tpos.ra.deg
            ph["TGT_DEC"] = tpos.dec.deg
            ph["NSATUR"] = (int(np.sum(exp["saturated"])), "exposures with saturation flags on target")
            ph["CONTAM"] = (float(np.mean(exp["contam_fraction"])), "mean fraction of contamination-flagged px")
            ph["BADFRAC"] = (float(np.mean(exp["bad_fraction"])), "mean fraction of rejected px")
            ph["REJBITS"] = (",".join(map(str, REJECT_BITS)), "FLAGS bits masked")
            ph["COMBINE"] = (f"weighted mean 1/var, {CLIP_SIGMA}-sigma clip (median, MAD)", "")
            ph["BKGSUB"] = ("ZODI + clipped median", "")
            ph["FILLNOTE"] = ("FILLED = n exposures with saturated px interpolated", "")
            ph["CREATED"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            hdul = fits.HDUList([
                primary,
                fits.ImageHDU(mean.astype(np.float32), hdr, name="IMAGE"),
                fits.ImageHDU(var.astype(np.float32), hdr, name="VARIANCE"),
                fits.ImageHDU(nimg, hdr, name="NIMAGES"),
                fits.ImageHDU(np.sum(holes, axis=0).astype(np.int16), hdr, name="FILLED"),
                fits.BinTableHDU(exp, name="EXPOSURES"),
            ])
            path = out_dir / f"{epoch}_D{det}.fits"
            hdul.writeto(path, overwrite=True)
            written.append(path)
            log.info("%s D%d: %d exposures, λ %.3f-%.3f um, saturated %d, clipped px %d -> %s",
                     epoch, det, len(ims), ph["WAVEMIN"], ph["WAVEMAX"], ph["NSATUR"], n_clipped, path.name)
    return written


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="barnard")
    p.add_argument("--fov", type=float, default=None, help="override fov_arcmin from targets.yaml")
    a = p.parse_args()
    stack_target(a.target, a.fov)


if __name__ == "__main__":
    main()
