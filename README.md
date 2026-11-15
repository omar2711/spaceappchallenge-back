# Ruta del Agua - Backend

Backend FastAPI para el desafío **Planet X SPHEREx**.

## Requisitos

- Python 3.11 o superior
- PowerShell

Verificar Python:

```powershell
python --version
```

## Instalación

Ejecutar desde la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,spherex]"
```

`spherex` instala lo que necesitan los endpoints de SPHEREx (astropy, photutils, etc.).

Si PowerShell bloquea la activación:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Iniciar el backend

Con el entorno virtual activado:

```powershell
uvicorn app.main:app --reload
```

URLs:

- API: <http://127.0.0.1:8000>
- Documentación: <http://127.0.0.1:8000/docs>
- Salud: <http://127.0.0.1:8000/health>

Detener el servidor con `Ctrl+C`.

Salir del entorno virtual:

```powershell
deactivate
```

## Pipeline de datos SPHEREx

La carpeta `pipeline/` genera las imágenes que usa la web: baja recortes de SPHEREx desde IRSA, los combina por
pasada × detector y exporta WebP + `manifest.json` en `public-data/targets/`. Ese contenido ya está en el repo,
así que la API y el frontend no necesitan correr el pipeline.

Tiene dependencias propias, más pesadas que las de la API (astropy, astroquery, reproject):

```powershell
python -m pip install -r pipeline/requirements.txt
python -m pipeline.build --all --max-per-group 6   # regenera los 5 objetivos (~2 GB de descarga)
python -m pipeline.report                          # validación por objetivo
```

- Cómo consumir los datos (API, frontend, análisis): [pipeline/README.md](pipeline/README.md)
- Contrato del manifest: [pipeline/manifest.schema.json](pipeline/manifest.schema.json)
- Estado y pendientes: [docs/pipeline_estado.md](docs/pipeline_estado.md)

## Endpoints SPHEREx

Hay que arrancar el servidor desde la raíz del repo; usa `public-data/` y `data/`.

| Método y ruta | Qué hace |
|---|---|
| `POST /custom` | Body `{"ra", "dec", "fov_arcmin"=3, "max_exposures_per_group"=2}`. Lanza o reutiliza un campo para esas coordenadas y responde 202 con `job_id` y `state`. Responde 422 si la entrada es inválida |
| `GET /custom/{job_id}` | `state`: `pending`, `processing` (con `progress` %), `ready` (con `manifest_url`) o `error`. Responde 404 si el `job_id` no existe |
| `GET /spectrum?field=&ra=&dec=&label=` | Espectro de cualquier posición dentro de un campo ya calculado (los 5 objetivos, `hl_tau`, `trapezium`, `m42` o un `job_id`). Usa solo la caché y responde en ~0.1–1.5 s. Errores: 404 (campo desconocido), 409 (campo sin preparar), 422 (posición fuera del campo) |
| `GET /fields` | Campos disponibles para `/spectrum` |
| `GET /data/...` | `public-data/` como archivos estáticos. Por ejemplo `/data/targets/index.json`, `/data/targets/barnard/manifest.json`, `/data/custom/presets.json`, `/data/catalogs/splices.json` |

**Requisitos de datos en el servidor:**
- `/custom` descarga de IRSA, así que necesita internet. Un campo nuevo tarda ~3 minutos.
- `/spectrum` necesita los campos preparados en `data/analysis/fields/` (~50 MB en total). Se generan con `python -m analysis.field_spectrum --prepare-all`, a partir de la caché de recortes en `data/raw/`.

Las pruebas (`pytest`) usan solo datos en caché.

## Modo demo local (sin internet)

Es el plan principal para la presentación: la red del lugar puede fallar.

```powershell
demo.bat                                  # o: .venv\Scripts\python -m app.demo
```

- **Qué hace:** verifica los datos, bloquea toda conexión de red saliente y prueba cada endpoint. Si todo está bien, levanta la API en `http://localhost:8000` (Swagger en `/docs`).
- **Desde otro equipo de la misma red** (por ejemplo, la laptop del frontend): `http://<IP-de-esta-laptop>:8000`.
- **Solo verificar, sin levantar el servidor:** `demo.bat --check`.

**Requisitos (una vez, con internet):**
- `pip install -e ".[dev,spherex]"`.
- Las efemérides en `data/ephemeris/`.
- Los campos preparados en `data/analysis/fields/`. Vienen en el *data bundle*; ver `docs/DEPLOY.md`.

**Límites:**
- En este modo, `POST /custom` solo devuelve los campos precalculados (`/data/custom/presets.json`). Para coordenadas nuevas responde 503, porque generarlas requiere IRSA.
- Los mosaicos de Mars Trek que use el frontend vienen de servidores de NASA y también necesitan internet.
