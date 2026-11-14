"""Per-target validation report from the stacks and manifest.

    .venv/Scripts/python -m pipeline.report            # all exported targets
    .venv/Scripts/python -m pipeline.report --target barnard

- Movers: flux-weighted centroid per epoch vs. expected shift from proper motion.
- Everyone: background-subtracted aperture flux per epoch and detector (a light-curve preview; saturated
  cores are interpolated, so treat bright-star fluxes as lower limits).
"""
import argparse
import json
from itertools import combinations

import numpy as np
from astropy.io import fits

from pipeline.export import PUBLIC_ROOT
from pipeline.stack import PIXEL_SCALE_ARCSEC, PROCESSED_ROOT


def centroid(img, x0, y0, r=3):
    xi, yi = int(round(x0)), int(round(y0))
    sub = img[yi - r:yi + r + 1, xi - r:xi + r + 1]
    sub = np.nan_to_num(sub - np.nanmedian(img))
    sub[sub < 0] = 0
    if sub.sum() <= 0:
        return np.array([np.nan, np.nan])
    yy, xx = np.mgrid[yi - r:yi + r + 1, xi - r:xi + r + 1]
    return np.array([(sub * xx).sum() / sub.sum(), (sub * yy).sum() / sub.sum()])


def aperture(img, x0, y0, r=2.5, r_in=6, r_out=9):
    yy, xx = np.indices(img.shape)
    d = np.hypot(xx - x0, yy - y0)
    ann = img[(d >= r_in) & (d <= r_out)]
    bkg = np.nanmedian(ann)
    ap = (d <= r) & np.isfinite(img)
    peak_snr = np.nanmax(img[d <= 1.5]) / (1.4826 * np.nanmedian(np.abs(ann - bkg)))
    return float(np.sum(img[ap] - bkg)), float(peak_snr)


def report(target_id):
    m = json.loads((PUBLIC_ROOT / target_id / "manifest.json").read_text(encoding="utf-8"))
    pm = np.hypot(m["proper_motion_mas_yr"]["pmra"], m["proper_motion_mas_yr"]["pmdec"])
    print(f"\n### {m['name']} ({target_id}) — kind {m['kind']}, pm {pm / 1000:.2f}\"/yr")
    print("epochs:", ", ".join(f"{e['id']} {e['date_start'][:10]}..{e['date_end'][:10]}" for e in m["epochs"]))
    epochs = [e["id"] for e in m["epochs"]]
    print(f"{'det':4}" + "".join(f"{e:>24}" for e in epochs) + "   (n_img / flux MJy/sr*px / peak S/N / contam)")
    errs = []
    for d in m["detectors"]:
        cells, cen, exp = {}, {}, {}
        for f in d["frames"]:
            with fits.open(PROCESSED_ROOT / target_id / f["fits"]) as h:
                p, img = h[0].header, h["IMAGE"].data.astype(float)
            flux, snr = aperture(img, p["TGT_X"], p["TGT_Y"])
            cells[f["epoch"]] = f"{f['n_images']:>3} {flux:9.1f} {snr:6.1f} {f['flags_fraction']:.2f}"
            cen[f["epoch"]] = centroid(img, p["TGT_X"], p["TGT_Y"])
            exp[f["epoch"]] = np.array([p["TGT_X"], p["TGT_Y"]])
        print(f"D{d['id']:<3}" + "".join(f"{cells.get(e, '-'):>24}" for e in epochs))
        for a, b in combinations([e for e in epochs if e in cen], 2):
            meas, want = cen[b] - cen[a], exp[b] - exp[a]
            if np.all(np.isfinite(meas)):
                errs.append((d["id"], a, b, np.hypot(*meas) * PIXEL_SCALE_ARCSEC,
                             np.hypot(*want) * PIXEL_SCALE_ARCSEC, np.hypot(*(meas - want)) * PIXEL_SCALE_ARCSEC))
    if pm > 500 and errs:
        e = np.array([x[5] for x in errs])
        first, last = epochs[0], epochs[-1]
        span = [x for x in errs if x[1] == first and x[2] == last]
        print(f"motion {first}->{last}: " + ", ".join(f"D{x[0]} {x[3]:.1f}\" (exp {x[4]:.1f}\")" for x in span))
        print(f"centroid error vs proper motion: median {np.median(e):.2f}\", max {e.max():.2f}\" over {len(e)} pairs")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target")
    a = p.parse_args()
    ids = [a.target] if a.target else sorted(x.parent.name for x in PUBLIC_ROOT.glob("*/manifest.json"))
    for tid in ids:
        report(tid)


if __name__ == "__main__":
    main()
