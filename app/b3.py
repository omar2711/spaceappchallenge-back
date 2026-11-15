"""Endpoints B3: Luna, Gaia, Cochabamba y Marte. Todo funciona sin internet (datos y efemérides locales)."""
from fastapi import APIRouter, HTTPException, Query

from b3 import cochabamba, gaia, mars, moon
from b3.ephemeris import EphemerisMissing

router = APIRouter()


@router.get("/moon/sites", tags=["moon"], summary="Sitios lunares: Apollo 11–17 y regiones candidatas de Artemis III")
def moon_sites() -> dict:
    return moon.sites()


@router.get("/moon/visibility", tags=["moon"], summary="Sol y Tierra vistos desde un sitio lunar")
def moon_visibility(site: str = Query(..., description="id de /moon/sites, p. ej. apollo11, haworth"),
                    start: str = Query(..., description="inicio UTC ISO: 2026-12-01 o 2026-12-01T06:00"),
                    days: float = Query(7, gt=0, le=moon.MAX_DAYS),
                    step_min: int = Query(30, ge=moon.MIN_STEP_MIN, le=moon.MAX_STEP_MIN)) -> dict:
    """Elevación/azimut del Sol y de la Tierra, horas de sol, ventanas con la Tierra visible y tiempo hasta el
    atardecer / ocultamiento de la Tierra. Horizonte de esfera lisa (sin relieve)."""
    try:
        return moon.visibility(site, start, days, step_min)
    except moon.SiteNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EphemerisMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/gaia", tags=["gaia"], summary="Estrellas Gaia DR3 del campo, propagadas a cada pasada (flechas)")
def gaia_field(field: str = Query(..., description="barnard, eps_ind_b, r_dra, rw_aur, wise0855, hl_tau, trapezium, m42")) -> dict:
    """`sources[].epochs[<pasada>].px` = posición en píxeles WebP de ese campo en la fecha media de la pasada
    (dibujar flechas entre pasadas cuando `arrow` es true)."""
    try:
        return gaia.load_field(field)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/visibility", tags=["cochabamba"], summary="¿Se ve desde Cochabamba esa noche?")
def cochabamba_visibility(ra: float = Query(..., ge=0, lt=360), dec: float = Query(..., ge=-90, le=90),
                          date: str | None = Query(None, description="fecha local YYYY-MM-DD (por defecto hoy)")) -> dict:
    """Curva de altura de mediodía a mediodía (hora local UTC-4), salida, puesta, culminación, mejor hora y si es
    observable (altura > 20° con el Sol bajo −12°)."""
    try:
        return cochabamba.visibility(ra, dec, date)
    except EphemerisMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/mars/marswalk", tags=["mars"], summary="Caminata por el cráter Jezero siguiendo a Perseverance")
def marswalk() -> dict:
    """Ruta (recorrido oficial simplificado), 4 paradas científicas, peligros y capas de Mars Trek (verificadas).
    También como estático en /data/mars/marswalk.json."""
    return mars.load()
