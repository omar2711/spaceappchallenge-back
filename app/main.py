"""Punto de entrada de la API de Ruta del Agua."""

from fastapi import FastAPI


app = FastAPI(
    title="Ruta del Agua API",
    description="API para la experiencia Planet X SPHEREx de Space Apps Cochabamba.",
    version="0.1.0",
)


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
