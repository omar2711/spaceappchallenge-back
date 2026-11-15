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
python -m pip install -e ".[dev]"
```

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

Endpoints de datos:

- `GET /api/v1/targets`: lista los cinco objetivos SPHEREx.
- `GET /api/v1/targets/{target_id}`: devuelve el `manifest.json` del objetivo.
- `GET /api/v1/targets/{target_id}/analysis`: devuelve diferencias y curvas de luz.
- `GET /api/v1/custom/presets`: lista los campos personalizados precalculados.
- `POST /api/v1/custom`: encola un campo nuevo a partir de RA/Dec.
- `GET /api/v1/custom/{job_id}`: consulta el progreso del campo solicitado.
- `GET /api/v1/visibility/cochabamba/{target_id}`: calcula visibilidad para una fecha UTC.
- `GET /api/v1/moon/sites`: lista sitios del polo sur y sitios Apollo.
- `GET /api/v1/moon/sites/{site_id}/conditions`: calcula Sol/Tierra para un sitio lunar.
- `GET /api/v1/mars/route`: devuelve la ruta educativa por Jezero.
- `GET /api/v1/ice`: devuelve la capa versionada de hielo para la demo.
- `GET /api/v1/comets/3i-atlas`: devuelve la ficha y fuentes del cometa.
- `/data/...`: sirve los WebP y JSON publicados desde `public-data/`.

Para permitir otro origen del frontend, define `API_CORS_ORIGINS` como una lista separada
por comas, por ejemplo `https://frontend.example,http://localhost:5173`.

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
