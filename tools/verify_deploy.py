"""Verify a deployed API end to end (status, timing, content type, CORS).

    .venv/Scripts/python tools/verify_deploy.py https://ruta-del-agua-api.onrender.com [--custom]

--custom also submits a NEW field to POST /custom and polls it (needs the server to reach IRSA, ~3-6 min).
"""
import json
import sys
import time

import requests

CHECKS = [
    ("GET", "/health", None),
    ("GET", "/", None),
    ("GET", "/docs", None),
    ("GET", "/openapi.json", None),
    ("GET", "/fields", None),
    ("GET", "/spectrum", {"field": "m42", "ra": 83.8088, "dec": -5.37298, "label": "BN/KL"}),
    ("GET", "/spectrum", {"field": "eps_ind_b", "ra": 331.12786, "dec": -56.77502}),
    ("GET", "/spectrum", {"field": "hl_tau", "ra": 67.900561, "dec": 18.228685}),
    ("GET", "/moon/sites", None),
    ("GET", "/moon/visibility", {"site": "haworth", "start": "2026-12-01", "days": 30, "step_min": 10}),
    ("GET", "/moon/visibility", {"site": "apollo11", "start": "2026-11-15T00:00", "days": 1, "step_min": 60}),
    ("GET", "/gaia", {"field": "barnard"}),
    ("GET", "/gaia", {"field": "m42"}),
    ("GET", "/visibility", {"ra": 83.8221, "dec": -5.3911, "date": "2026-11-14"}),
    ("GET", "/mars/marswalk", None),
    ("POST", "/custom", {"ra": 83.8201, "dec": -5.3876, "fov_arcmin": 4}),
    ("GET", "/custom/c2d9e7410cce7", None),
    ("GET", "/data/targets/index.json", None),
    ("GET", "/data/targets/barnard/manifest.json", None),
    ("GET", "/data/targets/barnard/S1_D1.webp", None),
    ("GET", "/data/targets/eps_ind_b/analysis.json", None),
    ("GET", "/data/targets/eps_ind_b/analysis/diff_S1_S2_D6.webp", None),
    ("GET", "/data/custom/presets.json", None),
    ("GET", "/data/custom/c2d9e7410cce7/manifest.json", None),
    ("GET", "/data/custom/c2d9e7410cce7/S1_D4.webp", None),
    ("GET", "/data/catalogs/splices.json", None),
    ("GET", "/data/catalogs/3i_atlas.json", None),
    ("GET", "/data/catalogs/gaia/eps_ind_b.json", None),
    ("GET", "/data/moon/sites.json", None),
    ("GET", "/data/mars/marswalk.json", None),
    # expected errors
    ("GET", "/spectrum", {"field": "nope", "ra": 1, "dec": 1}),
    ("GET", "/moon/visibility", {"site": "apollo11", "start": "2026-12-01", "days": 31}),
]
EXPECTED_ERRORS = {("/spectrum", "nope"): 404, ("/moon/visibility", 31): 422}


def expected_status(method, path, payload):
    if path == "/spectrum" and payload and payload.get("field") == "nope":
        return 404
    if path == "/moon/visibility" and payload and payload.get("days") == 31:
        return 422
    return 202 if method == "POST" else 200


def check(base, method, path, payload):
    t0 = time.time()
    if method == "GET":
        r = requests.get(base + path, params=payload, timeout=120, headers={"Origin": "https://example.vercel.app"})
    else:
        r = requests.post(base + path, json=payload, timeout=120, headers={"Origin": "https://example.vercel.app"})
    dt = time.time() - t0
    want = expected_status(method, path, payload)
    extra = ""
    if r.ok and r.headers.get("content-type", "").startswith("application/json"):
        body = r.json()
        if path == "/spectrum":
            extra = f"n_exp={body['n_exposures']} elapsed_s={body['elapsed_s']}"
        elif path == "/moon/visibility":
            extra = f"sun0={body['series']['sun_elevation_deg'][0]} earth0={body['series']['earth_elevation_deg'][0]}"
        elif path == "/visibility":
            extra = f"culm={body['target_events']['culmination_alt_deg']} observable={body['observable']}"
        elif path in ("/fields",):
            extra = f"prepared={sum(f['prepared'] for f in body)}/{len(body)}"
        elif path.startswith("/custom"):
            extra = f"state={body.get('state')}"
    return {"method": method, "path": path, "params": payload, "status": r.status_code, "expected": want,
            "ok": r.status_code == want, "seconds": round(dt, 2), "content_type": r.headers.get("content-type"),
            "cors": r.headers.get("access-control-allow-origin"), "bytes": len(r.content), "extra": extra}


def custom_new(base):
    payload = {"ra": 150.1, "dec": 2.2, "fov_arcmin": 2, "max_exposures_per_group": 1}  # COSMOS field, small job
    r = requests.post(base + "/custom", json=payload, timeout=120).json()
    jid, t0, last = r["job_id"], time.time(), None
    print(f"custom new job {jid}: {r['state']}")
    while time.time() - t0 < 900:
        s = requests.get(f"{base}/custom/{jid}", timeout=120).json()
        key = (s["state"], s.get("stage"))
        if key != last:
            print(f"  t={time.time() - t0:5.0f}s {s['state']:10s} {s.get('stage')} {s.get('progress')}% {s.get('message')}")
            last = key
        if s["state"] in ("ready", "error"):
            return s, time.time() - t0
        time.sleep(10)
    return s, time.time() - t0


def main():
    base = sys.argv[1].rstrip("/")
    results = [check(base, *c) for c in CHECKS]
    for r in results:
        p = "" if not r["params"] else "?" + "&".join(f"{k}={v}" for k, v in r["params"].items())
        print(f"{'OK ' if r['ok'] else 'ERR'} {r['status']} {r['seconds']:6.2f}s {r['method']:4s} {r['path']}{p[:70]}  "
              f"[{(r['content_type'] or '').split(';')[0]}, cors={r['cors']}] {r['extra']}")
    print(f"\n{sum(r['ok'] for r in results)}/{len(results)} OK")
    if "--custom" in sys.argv:
        s, dt = custom_new(base)
        print(f"custom new field: {s['state']} in {dt:.0f}s {s.get('manifest_url') or s.get('message')}")
        results.append({"custom_new": s, "seconds": round(dt, 1)})
    json.dump(results, open("data/verify_deploy.json", "w"), indent=1)


if __name__ == "__main__":
    main()
