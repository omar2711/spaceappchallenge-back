"""Punto de entrada de la API de Ruta del Agua."""

import json
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import astropy.units as u
from astropy.coordinates import AltAz, EarthLocation, get_sun
from astropy.time import Time
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from pipeline.custom import get_status, submit_custom
from pipeline.targets import position_at


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DATA_ROOT = PROJECT_ROOT / "public-data"
TARGETS_ROOT = PUBLIC_DATA_ROOT / "targets"
TARGET_INDEX_PATH = TARGETS_ROOT / "index.json"
CUSTOM_PRESETS_PATH = PUBLIC_DATA_ROOT / "custom" / "presets.json"
JOB_ID_PATTERN = re.compile(r"^c[a-f0-9]{12}$")
COCHABAMBA = EarthLocation.from_geodetic(
    lon=-66.157 * u.deg,
    lat=-17.3935 * u.deg,
    height=2_570 * u.m,
)
VISIBLE_ALTITUDE_DEG = 20.0
ASTRONOMICAL_NIGHT_ALTITUDE_DEG = -18.0


class CustomFieldRequest(BaseModel):
    """Parameters accepted for an arbitrary SPHEREx field."""

    model_config = ConfigDict(extra="forbid")

    ra: float = Field(ge=0, lt=360)
    dec: float = Field(ge=-90, le=90)
    fov_arcmin: float = Field(default=3, gt=0, le=6)
    max_exposures_per_group: int = Field(default=2, ge=1, le=30)


def _read_json(path: Path) -> dict[str, Any]:
    """Read a repository JSON artifact and fail explicitly if it is invalid."""
    try:
        with path.open(encoding="utf-8") as file:
            value = json.load(file)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Public data is not available") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=503, detail=f"Invalid public data: {path.name}") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=503, detail=f"Invalid public data shape: {path.name}")
    return value


def _target_entry(target_id: str) -> dict[str, Any]:
    index = _read_json(TARGET_INDEX_PATH)
    target = next((item for item in index.get("targets", []) if item.get("target_id") == target_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Unknown target: {target_id}")
    return target


def _target_manifest_path(target_id: str) -> Path:
    target = _target_entry(target_id)
    manifest = target.get("manifest")
    if not isinstance(manifest, str):
        raise HTTPException(status_code=503, detail=f"Target {target_id} has no manifest")
    path = (TARGETS_ROOT / manifest).resolve()
    if TARGETS_ROOT.resolve() not in path.parents or path.name != "manifest.json":
        raise HTTPException(status_code=503, detail=f"Invalid manifest path for {target_id}")
    return path


def _cors_origins() -> list[str]:
    configured = os.getenv("API_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


def _validate_job_id(job_id: str) -> None:
    if not JOB_ID_PATTERN.fullmatch(job_id):
        raise HTTPException(status_code=422, detail="Invalid custom job id")


def _observation_time(value: datetime | None) -> datetime:
    observed_at = value or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        return observed_at.replace(tzinfo=timezone.utc)
    return observed_at.astimezone(timezone.utc)


def _altitude_azimuth(coord, observed_at: datetime) -> tuple[float, float]:
    frame = AltAz(obstime=Time(observed_at), location=COCHABAMBA)
    horizontal = coord.transform_to(frame)
    return float(horizontal.alt.deg), float(horizontal.az.deg)


app = FastAPI(
    title="Ruta del Agua API",
    description="API para la experiencia Planet X SPHEREx de Space Apps Cochabamba.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

@app.get("/data/{file_path:path}", tags=["data"])
def get_public_data(file_path: str) -> FileResponse:
    """Sirve únicamente los archivos publicados dentro de public-data/."""
    root = PUBLIC_DATA_ROOT.resolve()
    path = (root / file_path).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Published file not found")
    media_type, _ = mimetypes.guess_type(path.name)
    if path.suffix.lower() == ".webp":
        media_type = "image/webp"
    return FileResponse(path, media_type=media_type or "application/octet-stream")


@app.get("/", tags=["system"])
def read_root() -> dict[str, str]:
    """Devuelve información básica de la API."""
    return {
        "name": "Ruta del Agua API",
        "status": "ok",
        "version": app.version,
        "docs": "/docs",
    }


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Comprueba que el servicio está disponible."""
    return {"status": "ok"}


@app.get("/api/v1/targets", tags=["targets"])
def list_targets() -> dict[str, Any]:
    """Lista los objetivos SPHEREx publicados."""
    return _read_json(TARGET_INDEX_PATH)


@app.get("/api/v1/targets/{target_id}", tags=["targets"])
def get_target(target_id: str) -> dict[str, Any]:
    """Devuelve el manifest completo de un objetivo."""
    _target_entry(target_id)
    return _read_json(_target_manifest_path(target_id))


@app.get("/api/v1/targets/{target_id}/analysis", tags=["analysis"])
def get_target_analysis(target_id: str) -> dict[str, Any]:
    """Devuelve diferencias, imágenes profundas y curvas de luz de un objetivo."""
    _target_entry(target_id)
    analysis_path = TARGETS_ROOT / target_id / "analysis.json"
    return _read_json(analysis_path)


@app.get("/api/v1/custom/presets", tags=["custom"])
def list_custom_presets() -> dict[str, Any]:
    """Lista los campos personalizados precalculados para la demo."""
    return _read_json(CUSTOM_PRESETS_PATH)


@app.post("/api/v1/custom", tags=["custom"])
def create_custom_field(request: CustomFieldRequest) -> JSONResponse:
    """Encola o reutiliza la generación de un campo SPHEREx personalizado."""
    try:
        status = submit_custom(
            request.ra,
            request.dec,
            request.fov_arcmin,
            request.max_exposures_per_group,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    status_code = 200 if status.get("state") == "ready" else 202
    return JSONResponse(content=status, status_code=status_code)


@app.get("/api/v1/custom/{job_id}", tags=["custom"])
def get_custom_field_status(job_id: str) -> dict[str, Any]:
    """Devuelve el estado de un trabajo personalizado."""
    _validate_job_id(job_id)
    status = get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Unknown custom job: {job_id}")
    return status


@app.get("/api/v1/visibility/cochabamba/{target_id}", tags=["visibility"])
def get_cochabamba_visibility(
    target_id: str,
    at: datetime | None = Query(default=None, description="UTC date and time; defaults to now"),
) -> dict[str, Any]:
    """Calcula si un objetivo está visible desde Cochabamba en una fecha dada."""
    _target_entry(target_id)
    observed_at = _observation_time(at)
    try:
        target_coord = position_at(target_id, observed_at)
        target_altitude, target_azimuth = _altitude_azimuth(target_coord, observed_at)
        sun_altitude, _ = _altitude_azimuth(get_sun(Time(observed_at)), observed_at)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid observation time: {exc}") from exc

    is_night = sun_altitude <= ASTRONOMICAL_NIGHT_ALTITUDE_DEG
    above_horizon = target_altitude >= VISIBLE_ALTITUDE_DEG
    visible = is_night and above_horizon
    if not is_night:
        reason = "daylight"
    elif not above_horizon:
        reason = "target_below_20_degrees"
    else:
        reason = "visible"
    return {
        "target_id": target_id,
        "observed_at": observed_at.isoformat(),
        "location": {
            "name": "Cochabamba",
            "latitude_deg": -17.3935,
            "longitude_deg": -66.157,
            "elevation_m": 2570,
        },
        "target": {
            "altitude_deg": round(target_altitude, 3),
            "azimuth_deg": round(target_azimuth, 3),
            "above_horizon": above_horizon,
        },
        "sun": {
            "altitude_deg": round(sun_altitude, 3),
            "astronomical_night": is_night,
        },
        "visible": visible,
        "reason": reason,
    }
