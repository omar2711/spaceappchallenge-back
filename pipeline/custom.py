"""Arbitrary coordinates: build the same products as the named targets for any RA/Dec.

Library (for the API, B3):
    from pipeline.custom import build_for_coords, submit_custom, get_status
    build_for_coords(ra, dec, fov_arcmin=3, max_exposures_per_group=6)  # blocking
    submit_custom(ra, dec, fov_arcmin=3, max_exposures_per_group=6)     # background, returns status dict
    get_status(job_id)                                                   # pending | processing | ready | error

CLI (also measures time and peak memory):
    .venv/Scripts/python -m pipeline.custom --ra 67.9101 --dec 18.2328 --fov 3

Outputs: public-data/custom/<job_id>/manifest.json + <epoch>_D<n>.webp (same contract as public-data/targets).
job_id is a hash of the rounded (ra, dec, fov, max_exposures_per_group), so repeated requests hit the cache.
"""
import argparse
import json
import logging
import shutil
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from pipeline.export import export_spec
from pipeline.fetch import fetch_spec
from pipeline.stack import stack_spec
from pipeline.targets import (CUSTOM_FOV_DEFAULT, CUSTOM_MAX_PER_GROUP_DEFAULT, PUBLIC_ROOT, custom_spec)

log = logging.getLogger("custom")

JOBS_DIR = Path("data/jobs")
DOWNLOAD_WORKERS = 4
# Overall progress (%) per stage: [start, end].
STAGES = {"query": (0, 5), "download": (5, 80), "stack": (80, 97), "export": (97, 100)}

# One build at a time: bounds memory and IRSA load. Extra requests queue as "pending".
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="custom-build")
_FUTURES = {}
_LOCK = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _status_path(job_id):
    return JOBS_DIR / f"{job_id}.json"


def _write_status(job_id, **fields):
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    path = _status_path(job_id)
    status = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"job_id": job_id, "created_at": _now()}
    status.update(fields, updated_at=_now())
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, indent=1), encoding="utf-8")
    tmp.replace(path)
    return status


def _manifest_rel(spec):
    return (spec.public_dir / "manifest.json").relative_to(PUBLIC_ROOT).as_posix()


def build_for_coords(ra, dec, fov_arcmin=CUSTOM_FOV_DEFAULT, max_exposures_per_group=CUSTOM_MAX_PER_GROUP_DEFAULT,
                     progress=None, keep_raw=False, workers=DOWNLOAD_WORKERS):
    """Blocking build for arbitrary coordinates. Returns {"job_id", "manifest", "cached", ...}.

    progress(percent, stage, message) is called during the build. Raw cutouts (~4 MB each) are deleted
    afterwards unless keep_raw=True; the stacks in data/processed/custom/<id>/ are kept for analysis.
    Raises ValueError (bad input) or LookupError (no SPHEREx coverage).
    """
    spec = custom_spec(ra, dec, fov_arcmin, max_exposures_per_group)
    manifest_path = spec.public_dir / "manifest.json"
    result = {"job_id": spec.id, "manifest": _manifest_rel(spec), "ra": spec.astrometry["ra"],
              "dec": spec.astrometry["dec"], "fov_arcmin": spec.fov_arcmin, "max_exposures_per_group": spec.max_per_group}
    if manifest_path.exists():
        return {**result, "cached": True}

    def stage_cb(stage, done, total):
        if progress:
            lo, hi = STAGES[stage]
            pct = lo + (hi - lo) * (done / total if total else 1)
            progress(round(pct, 1), stage, f"{stage} {done}/{total}")

    fetch_spec(spec, workers=workers, max_per_group=spec.max_per_group, progress=stage_cb)
    stack_spec(spec, progress=stage_cb)
    if progress:
        progress(STAGES["export"][0], "export", "writing WebP + manifest")
    manifest = export_spec(spec)
    if not keep_raw:
        for f in spec.raw_dir.glob("*.fits"):
            f.unlink(missing_ok=True)
    frames = sum(len(d["frames"]) for d in manifest["detectors"])
    return {**result, "cached": False, "epochs": [e["id"] for e in manifest["epochs"]], "frames": frames}


# ---------------------------------------------------------------- background jobs (API-facing)

def _run_job(job_id, ra, dec, fov_arcmin, max_per_group):
    _write_status(job_id, state="processing", progress=0.0, stage="query", message="starting")
    last = [0.0]

    def progress(pct, stage, message):
        if pct - last[0] >= 1 or stage == "export":  # throttle disk writes
            last[0] = pct
            _write_status(job_id, state="processing", progress=pct, stage=stage, message=message)

    try:
        res = build_for_coords(ra, dec, fov_arcmin, max_per_group, progress=progress)
        _write_status(job_id, state="ready", progress=100.0, stage="done", message="ready",
                      manifest=res["manifest"], frames=res.get("frames"), epochs=res.get("epochs"))
    except LookupError as exc:
        _write_status(job_id, state="error", message=str(exc), error="no_coverage")
    except Exception as exc:
        log.error("job %s failed:\n%s", job_id, traceback.format_exc())
        _write_status(job_id, state="error", message=str(exc)[:300], error=type(exc).__name__)
    finally:
        with _LOCK:
            _FUTURES.pop(job_id, None)


def submit_custom(ra, dec, fov_arcmin=CUSTOM_FOV_DEFAULT, max_exposures_per_group=CUSTOM_MAX_PER_GROUP_DEFAULT):
    """Start (or reuse) a background build. Returns the current status dict immediately.
    Raises ValueError for invalid input (the API should answer 422)."""
    spec = custom_spec(ra, dec, fov_arcmin, max_exposures_per_group)
    base = {"ra": spec.astrometry["ra"], "dec": spec.astrometry["dec"], "fov_arcmin": spec.fov_arcmin,
            "max_exposures_per_group": spec.max_per_group}
    if (spec.public_dir / "manifest.json").exists():
        return _write_status(spec.id, state="ready", progress=100.0, stage="done", message="cached",
                             manifest=_manifest_rel(spec), **base)
    with _LOCK:
        if spec.id in _FUTURES:  # already queued or running in this process
            return get_status(spec.id)
        status = _write_status(spec.id, state="pending", progress=0.0, stage="queued", message="waiting for a worker",
                               manifest=None, error=None, **base)
        _FUTURES[spec.id] = _EXECUTOR.submit(_run_job, spec.id, spec.astrometry["ra"], spec.astrometry["dec"],
                                             spec.fov_arcmin, spec.max_per_group)
    return status


def get_status(job_id):
    """Status dict for a job, or None if unknown. A job left 'processing' by a dead process is reported as
    error 'interrupted' (submit again to restart)."""
    path = _status_path(job_id)
    if not path.exists():
        return None
    status = json.loads(path.read_text(encoding="utf-8"))
    if status.get("state") in ("pending", "processing") and job_id not in _FUTURES:
        status = _write_status(job_id, state="error", error="interrupted",
                               message="build was interrupted (server restart?); submit again")
    return status


def clear_custom(job_id):
    """Delete every file of a custom job (raw, processed, public, status)."""
    for root in (Path("data/raw/custom"), Path("data/processed/custom"), PUBLIC_ROOT / "custom"):
        shutil.rmtree(root / job_id, ignore_errors=True)
    _status_path(job_id).unlink(missing_ok=True)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--ra", type=float, required=True)
    p.add_argument("--dec", type=float, required=True)
    p.add_argument("--fov", type=float, default=CUSTOM_FOV_DEFAULT)
    p.add_argument("--max-per-group", type=int, default=CUSTOM_MAX_PER_GROUP_DEFAULT)
    p.add_argument("--keep-raw", action="store_true")
    a = p.parse_args()

    import psutil
    proc = psutil.Process()
    peak = [proc.memory_info().rss]
    stop = threading.Event()

    def sample():
        while not stop.is_set():
            peak[0] = max(peak[0], proc.memory_info().rss)
            time.sleep(0.2)

    threading.Thread(target=sample, daemon=True).start()
    t0 = time.time()
    res = build_for_coords(a.ra, a.dec, a.fov, a.max_per_group, keep_raw=a.keep_raw,
                           progress=lambda pct, st, msg: log.info("%5.1f%% %s", pct, msg))
    stop.set()
    log.info("result: %s", res)
    log.info("total %.1f s, peak RSS %.0f MB", time.time() - t0, peak[0] / 2**20)


if __name__ == "__main__":
    main()
