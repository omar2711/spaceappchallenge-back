"""Generate docs/API_FRONTEND.md with REAL request/response examples (calls the app in-process).

    .venv/Scripts/python tools/gen_api_doc.py

Add an entry to ENDPOINTS / STATIC when a new endpoint or file appears, then rerun.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
OUT = ROOT / "docs" / "API_FRONTEND.md"

PRESETS = json.loads((ROOT / "public-data/custom/presets.json").read_text(encoding="utf-8"))["presets"]
M42 = next(p for p in PRESETS if p["id"] == "m42")

# (method, path, params_or_body, title, description)
ENDPOINTS = [
    ("GET", "/health", None, "Salud del servicio", "Úsalo para despertar el servidor público antes de la demo."),
    ("POST", "/custom", {"ra": M42["ra"], "dec": M42["dec"], "fov_arcmin": M42["fov_arcmin"]},
     "Campo para coordenadas arbitrarias",
     "Lanza (o reutiliza) la generación de un campo para RA/Dec y responde 202 al instante. Si ya existe, "
     "`state: ready` y `manifest_url`. Si no, consultar `GET /custom/{job_id}` cada ~2 s. Valores por defecto: "
     "`fov_arcmin=3` (máx. 6) y `max_exposures_per_group=2` (máx. 30). Un campo nuevo tarda ~3 min (descarga de IRSA). "
     "Entrada inválida → 422."),
    ("GET", f"/custom/{M42['job_id']}", None, "Estado de un campo",
     "`state`: `pending` | `processing` (con `progress` 0–100 y `stage`) | `ready` (con `manifest_url`) | `error` "
     "(`error`: `no_coverage`, `interrupted` u otro). `job_id` desconocido → 404."),
    ("GET", "/fields", None, "Campos con espectro disponible",
     "Campos válidos para `/spectrum`: los 5 objetivos y los presets (`hl_tau`, `trapezium`, `m42`)."),
    ("GET", "/spectrum", {"field": "m42", "ra": 83.8088, "dec": -5.37298, "label": "BN/KL"},
     "Espectro de cualquier posición dentro de un campo",
     "Usa solo datos en caché; responde en ~0.1–1.5 s. `spectra[]` trae un espectro por pasada y uno `combined`; "
     "`points[]` = `wavelength_um`, `flux` (mJy), `err`, `n`, `lower_limit` (saturado → dibujar como cota). "
     "`position.target_px` es la posición dentro de las imágenes del campo (coordenadas WebP). Errores: 404 campo "
     "desconocido, 409 campo sin preparar, 422 posición fuera del campo."),
]

ENDPOINTS += [
    ("GET", "/moon/sites", None, "Sitios lunares (Apollo y Artemis III)",
     "Apollo 11–17 (posición del módulo lunar, NSSDCA, marco DE421) y las 9 regiones candidatas de Artemis III "
     "(posición = centro IAU del accidente que nombra la región, NO el centro de la región: ver `position_type` y "
     "`position_uncertainty_km`). Cada sitio cita su fuente."),
    ("GET", "/moon/visibility", {"site": "haworth", "start": "2026-12-01", "days": 7, "step_min": 60},
     "Sol y Tierra desde un sitio lunar",
     "`days` ≤ 30, `step_min` 5–360 (por defecto 7 días cada 30 min); responde en < 0.2 s. `summary`: horas de sol, "
     "horas con la Tierra visible, ambas, y horas hasta el atardecer/amanecer y hasta que se oculta/sale la Tierra "
     "(null si no aplica en el rango). `windows`: intervalos (`open_start`/`open_end` = ya estaba / sigue al borde del "
     "rango). `series`: curvas para graficar. Horizonte de esfera lisa (sin relieve LOLA). Validado contra JPL "
     "Horizons (< 0.001°). Errores: 404 sitio, 422 parámetros."),
]

ENDPOINTS += [
    ("GET", "/gaia", {"field": "barnard"}, "Estrellas Gaia DR3 del campo",
     "Para los 5 objetivos y los 3 presets: fuentes Gaia DR3 (G < 20) del campo con `pmra`, `pmdec`, `g_mag` y la "
     "posición propagada a la fecha media de cada pasada en `epochs[<id>]` (`ra`, `dec` y `px` en coordenadas WebP "
     "del campo). Dibujar flechas entre pasadas donde `arrow` es true (movimiento propio ≥ 20 mas/año). Fuente "
     "ordenada por brillo. 404 si el campo no existe."),
]

# (url path, title, description)
STATIC = [
    ("/data/targets/index.json", "Índice de los 5 objetivos", "Lista de objetivos con su `manifest`."),
    ("/data/targets/barnard/manifest.json", "Manifest de un objetivo",
     "Contrato en `pipeline/manifest.schema.json`. Para el video: recorrer `detectors[d].frames` (mismo detector, "
     "todas las pasadas); cada `file` es un WebP relativo a la carpeta del manifest. `target_px` en coordenadas "
     "WebP (origen arriba a la izquierda)."),
    ("/data/targets/barnard/S1_D1.webp", "Frame WebP", "39×39 px (6.15\"/px): mostrar ampliado con "
     "`image-rendering: pixelated`."),
    ("/data/targets/eps_ind_b/analysis.json", "Análisis (B2) de un objetivo",
     "Diferencias entre pasadas, imágenes profundas, curvas de luz, espectros y bandas. Contrato en "
     "`analysis/analysis.schema.json`; guía en `analysis/README.md`."),
    ("/data/custom/presets.json", "Campos de demo precalculados",
     "Botones de demo: enviar exactamente sus `ra`, `dec`, `fov_arcmin` y `max_exposures_per_group` a `POST /custom` "
     "para acertar la caché (o leer `manifest` directamente)."),
    (f"/data/{M42['manifest']}", "Manifest de un campo libre", "Mismo contrato que los objetivos, `kind: custom`."),
    ("/data/catalogs/splices.json", "Catálogo SPLICES (candidatas a hielo)",
     "Formato compacto `columns` + `rows`. Son candidatas, NO detecciones (ver `important`). Colorear por "
     "`ice_priority` (1 protoestrella embebida, 2 otra YSO, 3 otra)."),
    ("/data/catalogs/3i_atlas.json", "Cometa interestelar 3I/ATLAS", "Metadatos, enlaces de IRSA y resultados "
     "publicados de SPHEREx (sin imágenes procesadas)."),
]


def trim(obj, depth=0):
    """Shorten long lists/strings so examples stay readable."""
    if isinstance(obj, list):
        head = [trim(x, depth + 1) for x in obj[:2]]
        return head + ([f"... (+{len(obj) - 2} más)"] if len(obj) > 2 else [])
    if isinstance(obj, dict):
        return {k: trim(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, str) and len(obj) > 160:
        return obj[:157] + "..."
    return obj


def block(obj):
    return "```json\n" + json.dumps(trim(obj), indent=2, ensure_ascii=False) + "\n```"


def main():
    lines = [
        "# API Ruta del Agua — guía para el frontend",
        "",
        "> Generado con `python tools/gen_api_doc.py` llamando a la API real: los ejemplos son respuestas reales "
        "(listas recortadas a 2 elementos). No editar a mano: actualizar el script y regenerar.",
        "",
        "- **Base URL local (modo demo):** `http://localhost:8000`",
        "- **Base URL pública:** Render, ver `docs/DEPLOY.md` (plan gratuito: la primera petición tras 15 min sin uso tarda ~30–60 s; llamar antes a `/health`)",
        "- **Documentación interactiva:** `GET /docs` (Swagger) y `GET /openapi.json`.",
        "- **CORS:** abierto (`*`). Archivos estáticos bajo `/data/...` (la carpeta `public-data/` del repo).",
        "- **Convención de imágenes:** los WebP tienen origen arriba a la izquierda; `target_px` = `[x, y]` en esa "
        "convención; el norte arriba y el este a la izquierda.",
        "",
        "## Endpoints",
        "",
    ]
    for method, path, payload, title, desc in ENDPOINTS:
        if method == "GET":
            r = client.get(path, params=payload)
            req = f"GET {path}" + ("?" + "&".join(f"{k}={v}" for k, v in payload.items()) if payload else "")
        else:
            r = client.post(path, json=payload)
            req = f"POST {path}\nContent-Type: application/json\n\n{json.dumps(payload)}"
        lines += [f"### {title}: `{method} {path.split('?')[0] if '{' not in path else path}`", "", desc, "",
                  "Request:", "", "```http", req, "```", "", f"Response `{r.status_code}`:", "", block(r.json()), ""]
    lines += ["## Archivos estáticos", "", "| Ruta | Contenido |", "|---|---|"]
    for url, title, desc in STATIC:
        lines.append(f"| `{url}` | **{title}.** {desc} |")
    lines.append("")
    for url, title, _ in STATIC:
        if url.endswith(".json"):
            r = client.get(url)
            lines += [f"### `{url}`", "", f"Response `{r.status_code}`:", "", block(r.json()), ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"written {OUT}")


if __name__ == "__main__":
    main()
