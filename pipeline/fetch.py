"""Query SPHEREx (SIA) for a target and download cutouts in parallel, with a resumable local cache.

    .venv/Scripts/python -m pipeline.fetch --target barnard
"""
import argparse
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import astropy.units as u
import numpy as np
import requests
from astropy.io import fits
from astropy.table import Table
from astroquery.ipac.irsa import Irsa

from pipeline.explore_barnard import group_epochs, retry
from pipeline.targets import RAW_ROOT, target_spec  # noqa: F401  (RAW_ROOT re-exported)

log = logging.getLogger("fetch")

COLLECTIONS = ["spherex_dr1", "spherex_qr3"]
CUTOUT_MARGIN_ARCMIN = 1.0  # cutouts are fov + margin so reprojection has room


def cutout_name(row):
    return f"{row['obs_id']}_{str(row['energy_bandpassname'])[-2:]}.fits"


def query_images(center):
    # IRSA returned 502s for several minutes on 2026-11-14: be patient here.
    res = retry(lambda: Irsa.query_sia(pos=(center, 1 * u.arcsec), collection=COLLECTIONS), tries=10, wait=20)
    keep = ["obs_id", "energy_bandpassname", "obs_collection", "t_min", "t_max", "t_exptime",
            "em_min", "em_max", "access_url"]
    res = Table(res[keep])
    res["epoch"] = group_epochs(np.asarray(res["t_min"], dtype=float)).astype(str)
    res["detector"] = [int(str(b)[-1]) for b in res["energy_bandpassname"]]
    res["file"] = [cutout_name(r) for r in res]
    return res


def download_one(url, path, tries=5):
    """Each cutout is ~4 MB (the EPSF table dominates). IRSA answers 503 under load: back off and retry."""
    tmp = path.with_suffix(".part")
    for i in range(tries):
        try:
            with requests.get(url, stream=True, timeout=(30, 180)) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        f.write(chunk)
            with fits.open(tmp) as hdul:  # validate before accepting
                hdul["IMAGE"].data.shape
            tmp.replace(path)
            return True
        except Exception as exc:
            wait = min(45, 5 * 2 ** i) + random.uniform(0, 5)
            log.info("%s attempt %d failed (%s), retry in %.0fs", path.name, i + 1, str(exc)[:80], wait)
            time.sleep(wait)
    tmp.unlink(missing_ok=True)
    return False


def plan_downloads(images, out, max_per_group=None):
    """Round-robin over (epoch, detector) groups so every group gets data early; optional cap per group."""
    groups = {}
    for r in images:
        groups.setdefault((str(r["epoch"]), int(r["detector"])), []).append(r)
    queues = []
    for rows in groups.values():
        have = [r for r in rows if (out / r["file"]).exists()]
        missing = [r for r in rows if not (out / r["file"]).exists()]
        if max_per_group is not None:
            missing = missing[:max(0, max_per_group - len(have))]
        queues.append(missing)
    order = []
    while any(queues):
        for q in queues:
            if q:
                order.append(q.pop(0))
    return order


def fetch_target(target_id, workers=3, max_per_group=None):
    return fetch_spec(target_spec(target_id), workers, max_per_group)


def fetch_spec(spec, workers=3, max_per_group=None, progress=None):
    """Query + download cutouts for a Spec. progress(stage, done, total) is called if given.
    Raises LookupError if SPHEREx has no image covering the position."""
    target_id = spec.id
    center = spec.position_at("2026-01-01")
    out = spec.raw_dir
    out.mkdir(parents=True, exist_ok=True)
    if progress:
        progress("query", 0, 1)

    index_path = out / "images.ecsv"
    if index_path.exists():
        images = Table.read(index_path)
    else:
        images = query_images(center)
        if len(images) == 0:
            raise LookupError(f"no SPHEREx images cover RA {center.ra.deg:.5f} Dec {center.dec.deg:.5f}")
        images.meta["center_ra"], images.meta["center_dec"] = center.ra.deg, center.dec.deg
        images.write(index_path, overwrite=True)
    log.info("%s: %d images in index", target_id, len(images))

    size = (spec.fov_arcmin + CUTOUT_MARGIN_ARCMIN) / 60
    todo = plan_downloads(images, out, max_per_group)
    n_have = sum((out / r["file"]).exists() for r in images)
    log.info("%d already cached, %d to download (max per group: %s)", n_have, len(todo), max_per_group)
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(download_one, f"{r['access_url']}?center={center.ra.deg},{center.dec.deg}d&size={size}",
                            out / r["file"]): r["file"] for r in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            if fut.result():
                ok += 1
            else:
                fail += 1
                log.warning("gave up on %s", futs[fut])
            if i % 10 == 0 or i == len(futs):
                log.info("progress %d/%d (ok %d, failed %d)", i, len(futs), ok, fail)
            if progress:
                progress("download", i, len(futs))
    have = sum((out / r["file"]).exists() for r in images)
    log.info("%s: %d/%d cutouts cached", target_id, have, len(images))
    return images


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="barnard")
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--max-per-group", type=int, default=None, help="cap cutouts per (epoch, detector)")
    a = p.parse_args()
    fetch_target(a.target, a.workers, a.max_per_group)


if __name__ == "__main__":
    main()
