"""End-to-end build: fetch cutouts -> stack per (epoch x detector) -> export WebP + manifest.

    .venv/Scripts/python -m pipeline.build --target barnard
    .venv/Scripts/python -m pipeline.build --all --max-per-group 6
"""
import argparse
import logging
import time

from pipeline.export import export_target
from pipeline.fetch import fetch_target
from pipeline.stack import stack_target
from pipeline.targets import load_targets

log = logging.getLogger("build")


def build(target_id, max_per_group=None, workers=3, skip_fetch=False):
    t0 = time.time()
    if not skip_fetch:
        fetch_target(target_id, workers=workers, max_per_group=max_per_group)
    stack_target(target_id)
    manifest = export_target(target_id)
    frames = sum(len(d["frames"]) for d in manifest["detectors"])
    log.info("== %s done in %.1f min: %d epochs, %d frames", target_id, (time.time() - t0) / 60,
             len(manifest["epochs"]), frames)
    return manifest


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--target")
    g.add_argument("--all", action="store_true")
    p.add_argument("--max-per-group", type=int, default=None)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--skip-fetch", action="store_true", help="only stack + export cached cutouts")
    a = p.parse_args()
    ids = list(load_targets()) if a.all else [a.target]
    failed = []
    for tid in ids:
        try:
            build(tid, a.max_per_group, a.workers, a.skip_fetch)
        except Exception:
            log.exception("== %s FAILED", tid)
            failed.append(tid)
    if failed:
        raise SystemExit(f"failed targets: {', '.join(failed)}")


if __name__ == "__main__":
    main()
