"""Modo demo local SIN internet: un solo comando para la presentación.

    .venv\\Scripts\\python -m app.demo            # verifica datos y levanta la API en http://localhost:8000
    .venv\\Scripts\\python -m app.demo --check    # solo verifica, con TODA conexión de red saliente bloqueada

Activa RDA_OFFLINE=1: POST /custom solo sirve campos ya calculados (presets) y responde 503 para coordenadas
nuevas; todo lo demás (5 objetivos, presets, espectros, catálogos, B3) es local.
"""
import argparse
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Every request the demo must answer without internet. Extend when adding endpoints (and docs/API_FRONTEND.md).
DEMO_CHECKS = [
    ("GET", "/health", None),
    ("GET", "/data/targets/index.json", None),
    ("GET", "/data/targets/barnard/manifest.json", None),
    ("GET", "/data/targets/barnard/S1_D1.webp", None),
    ("GET", "/data/targets/eps_ind_b/analysis.json", None),
    ("GET", "/data/custom/presets.json", None),
    ("GET", "/data/catalogs/splices.json", None),
    ("GET", "/data/catalogs/3i_atlas.json", None),
    ("GET", "/fields", None),
    ("POST", "/custom", {"ra": 83.8201, "dec": -5.3876, "fov_arcmin": 4}),
    ("GET", "/spectrum", {"field": "m42", "ra": 83.8088, "dec": -5.37298}),
    ("GET", "/spectrum", {"field": "eps_ind_b", "ra": 331.12786, "dec": -56.77502}),
    ("GET", "/moon/sites", None),
    ("GET", "/gaia", {"field": "barnard"}),
    ("GET", "/gaia", {"field": "m42"}),
    ("GET", "/moon/visibility", {"site": "haworth", "start": "2026-12-01", "days": 30, "step_min": 10}),
]

REQUIRED = [
    "public-data/targets/index.json",
    "public-data/custom/presets.json",
    "data/ephemeris/de421.bsp",
    "data/ephemeris/moon_pa_de421_1900-2050.bpc",
    "data/ephemeris/moon_080317.tf",
    "data/ephemeris/pck00008.tpc",
]


def block_network():
    """Refuse any connection that is not to this machine: proves the demo makes no external calls."""
    real_connect = socket.socket.connect

    def guarded(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise OSError(f"[demo offline] blocked outgoing connection to {address}")
        return real_connect(self, address)

    socket.socket.connect = guarded
    socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(OSError(f"[demo offline] blocked {a[0]}"))


def check():
    missing = [p for p in REQUIRED if not (ROOT / p).exists()]
    fields_dir = ROOT / "data/analysis/fields"
    prepared = sorted(d.name for d in fields_dir.iterdir()) if fields_dir.exists() else []
    print(f"Campos preparados para /spectrum: {prepared or 'NINGUNO'}")
    if missing:
        print("FALTAN archivos:", *missing, sep="\n  ")
        print("Ver docs/DEPLOY.md (descargar data-bundle) o correr el pipeline.")
        return False
    block_network()
    from fastapi.testclient import TestClient  # imported after blocking: nothing may phone home

    from app.main import app
    client = TestClient(app)
    ok = True
    for method, path, payload in DEMO_CHECKS:
        r = client.get(path, params=payload) if method == "GET" else client.post(path, json=payload)
        good = r.status_code < 400
        ok &= good
        print(f"  {'OK ' if good else 'ERR'} {r.status_code} {method} {path} {payload or ''}")
    print("Verificación sin red:", "TODO OK" if ok else "HAY ERRORES")
    return ok


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="solo verificar (red bloqueada) y salir")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = visible para otros equipos de la red local")
    a = p.parse_args()
    os.chdir(ROOT)
    os.environ["RDA_OFFLINE"] = "1"
    if a.check:
        sys.exit(0 if check() else 1)
    if not check():
        sys.exit(1)
    import uvicorn
    print(f"\nAPI demo (sin internet) en http://localhost:{a.port}  ·  docs: http://localhost:{a.port}/docs")
    print("Desde otro equipo de la misma red: http://<IP-de-esta-laptop>:%d" % a.port)
    uvicorn.run("app.main:app", host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()
