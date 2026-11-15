"""Deep images: combine many exposures into one, either on a fixed sky grid or co-moving with the target.

    .venv/Scripts/python -m pipeline.deep --target wise0855 --detectors 5 6 --comoving

--comoving ("shift-and-add") centres every exposure on the target's position at that exposure's time,
so a faint fast mover piles up at the centre while fixed stars smear along the reversed track.
Outputs data/processed/<target>/deep_D<dets>[_comoving].fits and a PNG in data/checks/.
"""
import argparse
import logging

import matplotlib
import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy.time import Time
from astropy.visualization import AsinhStretch, ImageNormalize
from reproject import reproject_interp

from pipeline.fetch import RAW_ROOT
from pipeline.stack import PROCESSED_ROOT, combine, load_exposure, make_grid
from pipeline.targets import get_target, position_at, reference_coord

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

log = logging.getLogger("deep")


def deep_image(target_id, detectors, comoving=False):
    raw = RAW_ROOT / target_id
    images = Table.read(raw / "images.ecsv")
    images = images[[(raw / f).exists() and int(d) in detectors for f, d in zip(images["file"], images["detector"])]]
    fov = get_target(target_id)["fov_arcmin"]
    t_mean = Time(np.mean(np.asarray(images["t_min"], dtype=float)), format="mjd")
    fixed_grid, shape = make_grid(position_at(target_id, t_mean), fov)
    c_ref = reference_coord(target_id)

    ims, vrs = [], []
    for r in images:
        t_mid = Time((float(r["t_min"]) + float(r["t_max"])) / 2, format="mjd")
        c = c_ref.apply_space_motion(new_obstime=t_mid)
        try:
            sci, var, _, wcs, _ = load_exposure(raw / r["file"], c)
        except Exception as exc:
            log.warning("skipping %s: %s", r["file"], exc)
            continue
        grid = make_grid(position_at(target_id, t_mid), fov)[0] if comoving else fixed_grid
        im, fp = reproject_interp((sci, wcs), grid, shape_out=shape)
        vr, _ = reproject_interp((var, wcs), grid, shape_out=shape)
        im[fp < 0.99] = np.nan
        # Normalise each exposure by its own noise so detectors with different units/levels combine fairly.
        ims.append(im)
        vrs.append(vr)
    mean, var, nimg, _ = combine(ims, vrs)
    snr = mean / np.sqrt(var)
    tag = "".join(map(str, detectors)) + ("_comoving" if comoving else "")
    out = PROCESSED_ROOT / target_id / f"deep_D{tag}.fits"
    hdr = fixed_grid.to_header()
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(mean.astype(np.float32), hdr, name="IMAGE"),
                  fits.ImageHDU(snr.astype(np.float32), hdr, name="SNR"),
                  fits.ImageHDU(nimg, hdr, name="NIMAGES")]).writeto(out, overwrite=True)
    c = (shape[0] - 1) / 2
    yy, xx = np.indices(shape)
    near = np.hypot(xx - c, yy - c) <= 1.5
    log.info("%s deep D%s: %d exposures, peak S/N within 1.5 px of target = %.1f -> %s",
             target_id, tag, len(ims), np.nanmax(snr[near]), out.name)
    return mean, snr, len(ims)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True)
    p.add_argument("--detectors", type=int, nargs="+", default=[1, 2, 3, 4, 5, 6])
    p.add_argument("--comoving", action="store_true")
    a = p.parse_args()
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.6))
    for ax, como in zip(axes, [False, True]):
        mean, snr, n = deep_image(a.target, a.detectors, como)
        ax.imshow(snr, origin="lower", cmap="gray", norm=ImageNormalize(vmin=-3, vmax=15, stretch=AsinhStretch(0.1)))
        c = (snr.shape[0] - 1) / 2
        ax.plot(c, c, "o", mfc="none", mec="lime", ms=14)
        ax.set_title(f"{'co-moving' if como else 'fixed sky'}  D{a.detectors}  n={n}\n(S/N map)", fontsize=9)
        ax.set_xticks([]), ax.set_yticks([])
    fig.tight_layout()
    path = f"data/checks/{a.target}_deep_D{''.join(map(str, a.detectors))}.png"
    fig.savefig(path, dpi=90)
    log.info("saved %s", path)


if __name__ == "__main__":
    main()
