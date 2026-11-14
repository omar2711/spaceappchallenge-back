"""Visual check of the proposed FLAGS mask on Barnard cutouts.

Run from the repo root:
    .venv/Scripts/python -m pipeline.check_flags
Output: data/checks/barnard_flags.png
"""
import argparse
import logging
from pathlib import Path

import astropy.units as u
import matplotlib
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.visualization import AsinhStretch, ImageNormalize, PercentileInterval
from astropy.wcs import WCS
from astroquery.ipac.irsa import Irsa

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from pipeline.explore_barnard import BARNARD_GAIA_DR3, group_epochs, resolve_target, retry  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("check_flags")

RAW_DIR = Path("data/raw/barnard_check")
OUT = Path("data/checks/barnard_flags.png")
CUTOUT_SIZE_DEG = 4 / 60
DETECTORS = ["SPHEREx-D1", "SPHEREx-D3", "SPHEREx-D4", "SPHEREx-D6"]
PER_GROUP = 1

# Proposed mask (bit numbers from the FLAGS header MSKNnn keywords).
REJECT_BITS = {0: "TRANSIENT", 1: "OVERFLOW", 2: "SUR_ERROR", 6: "NONFUNC", 9: "MISSING_DATA",
               10: "HOT", 11: "COLD", 15: "NONLINEAR", 17: "PERSIST", 19: "OUTLIER",
               25: "STREAK", 26: "BLOOM", 27: "SNOWBALL"}
WARN_BITS = {7: "DICHROIC", 20: "CROSSTALK", 22: "GHOST", 23: "GHOST_FPA", 24: "GHOST_EXT", 28: "HALO"}
SOURCE_BIT = 21


def bitmask(bits):
    return sum(1 << b for b in bits)


def fetch_cutout(row, coord, cached_only=False):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{row['obs_id']}_{str(row['energy_bandpassname'])[-2:]}.fits"
    if not path.exists():
        if cached_only:
            raise FileNotFoundError(path.name)
        url = f"{row['access_url']}?center={coord.ra.deg},{coord.dec.deg}d&size={CUTOUT_SIZE_DEG}"
        log.info("downloading %s", path.name)

        def get():
            with fits.open(url) as hdul:
                hdul.writeto(path, overwrite=True)
        retry(get)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cached-only", action="store_true", help="use only cutouts already in data/raw")
    args = parser.parse_args()
    c_ref, _ = resolve_target(BARNARD_GAIA_DR3)
    probe = c_ref.apply_space_motion(new_obstime=Time("2026-01-01"))
    res = retry(lambda: Irsa.query_sia(pos=(SkyCoord(probe.ra, probe.dec), 1 * u.arcsec),
                                       collection=["spherex_dr1", "spherex_qr3"]))
    res["epoch"] = group_epochs(np.asarray(res["t_min"], dtype=float))
    epochs = sorted(set(res["epoch"]), key=lambda s: int(s[1:]))

    panels = []
    for det in DETECTORS:
        for ep in epochs:
            sel = res[(res["energy_bandpassname"] == det) & (res["epoch"] == ep)]
            got = 0
            for row in sel:
                if got == PER_GROUP:
                    break
                t = Time(float(row["t_min"]), format="mjd")
                c = c_ref.apply_space_motion(new_obstime=t)
                try:
                    panels.append((det, ep, t, c, fetch_cutout(row, c, args.cached_only)))
                    got += 1
                except FileNotFoundError:
                    continue
                except Exception as exc:  # IRSA 503s: skip this exposure, try the next one
                    log.warning("skipping %s %s: %s", row["obs_id"], det, exc)

    reject, warn = bitmask(REJECT_BITS), bitmask(WARN_BITS)
    n = len(panels)
    fig, axes = plt.subplots(len(DETECTORS), len(epochs), figsize=(3.2 * len(epochs), 3.4 * len(DETECTORS)))
    axes = np.atleast_2d(axes)
    print(f"\n{'panel':<16}{'reject%':>8}{'warn%':>7}{'source%':>8}  target: reject/warn/source  bits hit")
    for i, (det, ep, t, c, path) in enumerate(panels):
        ax = axes[i // len(epochs), i % len(epochs)]
        with fits.open(path) as hdul:
            img = hdul["IMAGE"].data.astype(float)
            flg = hdul["FLAGS"].data.astype(np.int64)
            x, y = WCS(hdul["IMAGE"].header).world_to_pixel(c)
        rej = (flg & reject) != 0
        wrn = ((flg & warn) != 0) & ~rej
        src = (flg & (1 << SOURCE_BIT)) != 0
        xi, yi = int(round(float(x))), int(round(float(y)))
        tgt = flg[yi - 1:yi + 2, xi - 1:xi + 2]  # 3x3 around the target
        hit = sorted({b for b in range(32) if np.any(flg & (1 << b))})
        print(f"{det[-2:]} {ep} {t.iso[:10]} {100 * rej.mean():7.1f}{100 * wrn.mean():7.1f}{100 * src.mean():8.1f}  "
              f"{int(np.any(tgt & reject))}/{int(np.any(tgt & warn))}/{int(np.any(tgt & (1 << SOURCE_BIT)))}  {hit}")
        norm = ImageNormalize(img[np.isfinite(img)], interval=PercentileInterval(99.5), stretch=AsinhStretch())
        ax.imshow(img, origin="lower", cmap="gray", norm=norm)
        overlay = np.zeros(img.shape + (4,))
        overlay[wrn] = [1, 0.85, 0, 0.45]
        overlay[rej] = [1, 0, 0, 0.75]
        ax.imshow(overlay, origin="lower")
        ax.contour(src, levels=[0.5], colors="cyan", linewidths=0.6)
        ax.plot(x, y, marker="o", mfc="none", mec="lime", ms=14, mew=1.2)
        ax.set_title(f"{det[-2:]} {ep} {t.iso[:10]}\nrechazo {100 * rej.mean():.1f}%  aviso {100 * wrn.mean():.1f}%", fontsize=8)
        ax.set_xticks([]), ax.set_yticks([])
    for j in range(n, axes.size):
        axes.flat[j].axis("off")
    fig.suptitle("Barnard: rojo = descartado, amarillo = aviso, cian = SOURCE, círculo verde = posición esperada", fontsize=10)
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=110)
    log.info("saved %s", OUT)


if __name__ == "__main__":
    main()
