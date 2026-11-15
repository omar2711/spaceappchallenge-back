"""Punto de entrada de la API de Ruta del Agua."""

import mimetypes

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.b3 import router as b3_router
from app.spherex import PUBLIC_DATA_DIR, STATIC_PREFIX
from app.spherex import router as spherex_router


app = FastAPI(
    title="Ruta del Agua API",
    description="API para la experiencia Planet X SPHEREx de Space Apps Cochabamba.",
    version="0.1.0",
)

# El frontend se publica en otro dominio (Vercel / GitHub Pages) y los datos son públicos.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])

app.include_router(spherex_router)
app.include_router(b3_router)

# public-data/ (manifests, WebP, analysis.json, catálogos) como archivos estáticos en /data.
# Windows no siempre registra .webp: sin esto se sirven como application/octet-stream.
mimetypes.add_type("image/webp", ".webp")
app.mount(STATIC_PREFIX, StaticFiles(directory=PUBLIC_DATA_DIR), name="data")


@app.get("/", tags=["system"])
def read_root() -> dict[str, str]:
    """Devuelve información básica de la API."""
    return {
        "name": "Ruta del Agua API",
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Comprueba que el servicio está disponible."""
    return {"status": "ok"}
