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
