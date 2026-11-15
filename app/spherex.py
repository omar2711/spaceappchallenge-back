"""Endpoints SPHEREx: campos por coordenadas, espectros en un campo y datos estáticos.

Usa pipeline/custom.py (trabajos en segundo plano) y analysis/field_spectrum.py (espectros desde la caché).
Las rutas relativas del pipeline (data/, public-data/) asumen que el proceso corre en la raíz del repo.
"""
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[1]
if Path.cwd().resolve() != REPO_ROOT:  # pipeline/analysis use paths relative to the repo root
    os.chdir(REPO_ROOT)

from analysis.field_spectrum import (FieldNotFound, FieldNotPrepared, list_fields,  # noqa: E402
                                     spectrum_in_field)
from pipeline.custom import get_status, submit_custom  # noqa: E402
from pipeline.targets import (CUSTOM_FOV_DEFAULT, CUSTOM_FOV_MAX, CUSTOM_MAX_PER_GROUP_DEFAULT,  # noqa: E402
                              CUSTOM_MAX_PER_GROUP_LIMIT)

PUBLIC_DATA_DIR = REPO_ROOT / "public-data"
STATIC_PREFIX = "/data"

router = APIRouter(tags=["spherex"])


class CustomRequest(BaseModel):
    ra: float = Field(..., ge=0, lt=360, description="Ascensión recta ICRS, grados")
    dec: float = Field(..., ge=-90, le=90, description="Declinación ICRS, grados")
    fov_arcmin: float = Field(CUSTOM_FOV_DEFAULT, gt=0, le=CUSTOM_FOV_MAX)
    max_exposures_per_group: int = Field(CUSTOM_MAX_PER_GROUP_DEFAULT, ge=1, le=CUSTOM_MAX_PER_GROUP_LIMIT)


def _with_urls(status: dict) -> dict:
    """Agrega la URL pública del manifest (servido como estático en /data)."""
    if status.get("manifest"):
        status = {**status, "manifest_url": f"{STATIC_PREFIX}/{status['manifest']}"}
    return status


@router.post("/custom", status_code=202, summary="Generar (o reutilizar) un campo para RA/Dec")
def create_custom(req: CustomRequest) -> dict:
    """Lanza el trabajo en segundo plano y responde al instante con su estado.
    Si el campo ya existe, responde `state: ready` (caché)."""
    try:
        status = submit_custom(req.ra, req.dec, req.fov_arcmin, req.max_exposures_per_group)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _with_urls(status)


@router.get("/custom/{job_id}", summary="Estado de un trabajo: pending | processing | ready | error")
def custom_status(job_id: str) -> dict:
    status = get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"unknown job_id '{job_id}'")
    return _with_urls(status)


@router.get("/fields", summary="Campos donde se puede pedir un espectro")
def fields() -> list[dict]:
    return list_fields()


@router.get("/spectrum", summary="Espectro de cualquier posición dentro de un campo ya calculado")
def spectrum(field: str = Query(..., description="barnard, eps_ind_b, ..., hl_tau, trapezium, m42 o un job_id"),
             ra: float = Query(..., ge=0, lt=360), dec: float = Query(..., ge=-90, le=90),
             label: str | None = Query(None, max_length=120)) -> dict:
    """Usa solo los recortes en caché del campo (no descarga nada)."""
    try:
        return spectrum_in_field(field, ra, dec, label)
    except FieldNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FieldNotPrepared as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
