"""T1: difference images between consecutive epochs of the same detector, plus deep (all-epoch) images.

All B1 stacks of a target share one TAN grid, so differences are pixel-to-pixel (no reprojection).
diff = k * B - A, after removing each image's clipped median; k = median(flux_A / flux_B) over bright,
unsaturated field stars away from the target (k = 1 and flagged if fewer than MIN_REF_STARS).
"""
import logging

import numpy as np
from astropy.stats import sigma_clipped_stats
from astropy.visualization import AsinhStretch
from photutils.aperture import CircularAnnulus, CircularAperture, aperture_photometry
from photutils.detection import find_peaks

from analysis.common import (PUBLIC_ROOT, diverging_rgb, epoch_key, load_manifest, load_stack, save_webp_gray,
                             save_webp_rgb)

log = logging.getLogger("analysis.diff")

REF_SNR = 10.0          # field star peak threshold, in units of the image's robust sigma
REF_MIN_SEP_PX = 5.0    # keep reference stars this far from the target (any epoch)
REF_EDGE_PX = 4
MIN_REF_STARS = 3
APER_R, ANN_IN, ANN_OUT = 2.0, 4.0, 7.0
DIFF_PERCENTILE = 99.5  # symmetric colour range per detector, shared by all its pairs
DEEP_STRETCH = (2.0, 99.5, 0.002)  # same choice as B1's export (percentiles, asinh a)


def _sky_sub(img):
    _, med, std = sigma_clipped_stats(img[np.isfinite(img)], sigma=3)
    return img - med, std


def _aper_flux(img, xy):
    ap = CircularAperture(xy, r=APER_R)
    ann = CircularAnnulus(xy, r_in=ANN_IN, r_out=ANN_OUT)
    flux = aperture_photometry(img, ap)["aperture_sum"].data
    bkg = np.array([np.nanmedian(m.multiply(img)[m.data > 0]) for m in ann.to_mask(method="center")])
    return flux - bkg * ap.area


def empirical_aperture_err(diff, avoid_xy, n=300, seed=0):
    """Robust std of aperture sums at random positions away from the target: the honest noise of a
    difference image (the propagated variance underestimates it, see docs/pipeline_fase5.md)."""
    rng = np.random.default_rng(seed)
    ny, nx = diff.shape
    xs = rng.uniform(ANN_OUT, nx - ANN_OUT, n)
    ys = rng.uniform(ANN_OUT, ny - ANN_OUT, n)
    far = np.hypot(xs - avoid_xy[0], ys - avoid_xy[1]) > REF_MIN_SEP_PX
    sums = _aper_flux(diff, list(zip(xs[far], ys[far])))
    _, _, std = sigma_clipped_stats(sums[np.isfinite(sums)], sigma=3)
    return float(std)


def _target_xy_fits(stack):
    h = stack["header"]
    return float(h["TGT_X"]), float(h["TGT_Y"])


def flux_scale(a, b, target_xys):
    """Return (k, n_stars) so that k*B matches A on bright unsaturated field stars."""
    img_a, std_a = _sky_sub(a["image"])
    peaks = find_peaks(np.nan_to_num(img_a), threshold=REF_SNR * std_a, box_size=5)
    if peaks is None:
        return 1.0, 0
    ny, nx = img_a.shape
    xy = []
    for x, y in zip(peaks["x_peak"], peaks["y_peak"]):
        if not (REF_EDGE_PX <= x < nx - REF_EDGE_PX and REF_EDGE_PX <= y < ny - REF_EDGE_PX):
            continue
        if any(np.hypot(x - tx, y - ty) < REF_MIN_SEP_PX for tx, ty in target_xys):
            continue
        box = (slice(y - 2, y + 3), slice(x - 2, x + 3))
        if a["filled"][box].any() or b["filled"][box].any():  # saturated cores are lower limits
            continue
        xy.append((x, y))
    if len(xy) < MIN_REF_STARS:
        return 1.0, len(xy)
    fa = _aper_flux(img_a, xy)
    fb = _aper_flux(_sky_sub(b["image"])[0], xy)
    ok = (fa > 0) & (fb > 0)
    if ok.sum() < MIN_REF_STARS:
        return 1.0, int(ok.sum())
    return float(np.median(fa[ok] / fb[ok])), int(ok.sum())


def position_angle(v):
    """Position angle (deg, east of north) of a pixel vector on the north-up, east-left grid."""
    return round(float(np.degrees(np.arctan2(-v[0], v[1])) % 360), 1)


def dipole(diff, x0, y0, r=3):
    """Centroids of the positive and negative lobes near (x0, y0) (FITS pixels)."""
    xi, yi = int(round(x0)), int(round(y0))
    sub = diff[yi - r:yi + r + 1, xi - r:xi + r + 1]
    yy, xx = np.mgrid[yi - r:yi + r + 1, xi - r:xi + r + 1]
    out = {}
    for name, w in (("pos", np.clip(np.nan_to_num(sub), 0, None)), ("neg", np.clip(-np.nan_to_num(sub), 0, None))):
        out[name] = (float((w * xx).sum() / w.sum()), float((w * yy).sum() / w.sum())) if w.sum() > 0 else None
    return out


def build_differences(target_id):
    m = load_manifest(target_id)
    out_dir = PUBLIC_ROOT / target_id / "analysis"
    epochs = sorted([e["id"] for e in m["epochs"]], key=epoch_key)
    pm = m["proper_motion_mas_yr"]
    diffs, deeps, checks = [], [], []
    for det in [d["id"] for d in m["detectors"]]:
        stacks = {e: load_stack(target_id, e, det) for e in epochs}
        stacks = {e: s for e, s in stacks.items() if s is not None}
        avail = [e for e in epochs if e in stacks]
        if not avail:
            continue
        target_xys = [_target_xy_fits(stacks[e]) for e in avail]

        # Difference images between consecutive available epochs.
        pairs = []
        for ea, eb in zip(avail, avail[1:]):
            a, b = stacks[ea], stacks[eb]
            k, n_ref = flux_scale(a, b, target_xys)
            img_a, _ = _sky_sub(a["image"])
            img_b, _ = _sky_sub(b["image"])
            diff = k * img_b - img_a
            noise = np.sqrt(k ** 2 * b["var"] + a["var"])
            pairs.append((ea, eb, k, n_ref, diff, noise, a, b))
        if pairs:
            # Shared colour range per detector (comparable pairs); median over pairs so one noisy pair
            # (e.g. an epoch with 3 exposures) does not wash out the others.
            limit = float(np.median([np.nanpercentile(np.abs(p[4]), DIFF_PERCENTILE) for p in pairs]))
            for ea, eb, k, n_ref, diff, noise, a, b in pairs:
                name = f"diff_{ea}_{eb}_D{det}.webp"
                save_webp_rgb(diverging_rgb(diff, limit), out_dir / name)
                xa, ya = _target_xy_fits(a)
                xb, yb = _target_xy_fits(b)
                xm, ym = (xa + xb) / 2, (ya + yb) / 2
                tgt_flux = float(_aper_flux(_sky_sub(a["image"])[0], [(xa, ya)])[0])
                res = float(_aper_flux(diff, [(xm, ym)])[0])
                res_err = empirical_aperture_err(diff, (xm, ym))
                entry = {
                    "detector": det, "from": ea, "to": eb, "file": f"analysis/{name}",
                    "range": [-round(limit, 5), round(limit, 5)], "units": "MJy/sr",
                    "flux_scale": round(k, 4), "n_ref_stars": n_ref,
                    "scale_method": "field_stars" if n_ref >= MIN_REF_STARS else "none (k=1)",
                    "mean_wavelength_um": [round(float(np.mean(a["wavelengths_um"])), 4),
                                           round(float(np.mean(b["wavelengths_um"])), 4)],
                    "target_residual": {
                        "flux": round(res, 4), "err": round(res_err, 4),
                        "fraction_of_target": round(res / tgt_flux, 4) if tgt_flux > 0 else None,
                        "significance_sigma": round(abs(res) / res_err, 1) if res_err > 0 else None,
                        "significant": bool(res_err > 0 and abs(res) > 5 * res_err),
                    },
                }
                exp = np.subtract((xb, yb), (xa, ya))
                d = dipole(diff, xm, ym)
                if d["pos"] and d["neg"]:
                    v = np.subtract(d["pos"], d["neg"])
                    entry["dipole"] = {
                        "separation_px": round(float(np.hypot(*v)), 3),
                        "position_angle_deg": position_angle(v),
                        "expected_shift_px": round(float(np.hypot(*exp)), 3),
                        "expected_position_angle_deg": position_angle(exp),
                        "note": "Negative lobe = old position, positive = new. For shifts below the PSF size the "
                                "lobe separation reflects the PSF width; the direction is what validates motion.",
                    }
                lam = entry["mean_wavelength_um"]
                caveats = []
                if abs(lam[1] - lam[0]) / np.mean(lam) > 0.01:
                    caveats.append("wavelength_mismatch")
                if any(s_["filled"][int(round(y)) - 2:int(round(y)) + 3, int(round(x)) - 2:int(round(x)) + 3].any()
                       for s_, x, y in ((a, xa, ya), (b, xb, yb))):
                    caveats.append("saturated_target")
                if n_ref < MIN_REF_STARS:
                    caveats.append("few_reference_stars")
                if np.hypot(*exp) > 0.3:
                    caveats.append("moving_target")
                entry["caveats"] = caveats
                diffs.append(entry)
                checks.append(entry)

        # Deep image: inverse-variance weighted mean of all epochs of this detector.
        ims = np.array([stacks[e]["image"] for e in avail])
        w = np.array([1 / stacks[e]["var"] for e in avail])
        w[~np.isfinite(ims) | ~np.isfinite(w)] = 0
        deep = np.nansum(np.nan_to_num(ims) * w, axis=0) / np.where(w.sum(0) > 0, w.sum(0), np.nan)
        lo, hi = np.nanpercentile(deep, DEEP_STRETCH[:2])
        x = AsinhStretch(a=DEEP_STRETCH[2])(np.clip((np.nan_to_num(deep, nan=lo) - lo) / (hi - lo), 0, 1))
        name = f"deep_D{det}.webp"
        save_webp_gray(x, out_dir / name)
        deeps.append({"detector": det, "file": f"analysis/{name}", "epochs": avail,
                      "stretch": {"method": "asinh", "a": DEEP_STRETCH[2], "limits": [round(float(lo), 5), round(float(hi), 5)]},
                      "note": "Fixed-sky mean of all epochs: a moving target appears elongated along its track."})
        log.info("%s D%d: %d diffs, deep from %s", target_id, det, len(pairs), avail)
    return {"difference_images": diffs, "deep_images": deeps,
            "proper_motion_mas_yr": pm}
