"""Endpoints B3: Luna, Gaia, Cochabamba y Marte. Todo funciona sin internet (datos y efemérides locales)."""
from fastapi import APIRouter, HTTPException, Query

from b3 import moon
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
