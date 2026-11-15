"""Verified SIMBAD astrometry with explicit epoch propagation, separate from NASA data."""

from io import BytesIO

import httpx
import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table
from astropy.time import Time
from pydantic import Field

from .archive import utc_now
from .models import Contract, Number, Positive
from .observation_models import Target

# Official mirror recommended by CDS during the November 2026 service outage.
SIMBAD_TAP = "https://simbad.cfa.harvard.edu/simbad/sim-tap/sync"
TARGET_NAMES = {
    "Barnard's Star": "GJ 699",
    "Epsilon Indi B": "eps Ind B",
    "WISE 0855": "WISE J085510.83-071442.5",
    "RW Aurigae": "RW Aur",
    "R Draconis": "R Dra",
}


class Astrometry(Contract):
    reference: Target
    resolved_name: str
    reference_epoch_jyear: Number = 2000.0
    pm_ra_cosdec_mas_yr: Number | None
    pm_dec_mas_yr: Number | None
    parallax_mas: Positive | None = None
    radial_velocity_km_s: Number | None = None
    coordinate_bibcode: str | None = None
    proper_motion_bibcode: str | None = None
    retrieved_at_utc: str
    query: str
    warnings: list[str] = Field(default_factory=list)


def resolve_target(target_id: str, client: httpx.Client) -> Astrometry:
    """Small SIMBAD TAP query; SIMBAD basic coordinates are ICRS epoch J2000.

    Exact aliases are fixed here, never interpolated from arbitrary ADQL input.
    Missing proper motion is preserved; epoch propagation then refuses to proceed.
    """
    alias = TARGET_NAMES[target_id]
    query = ("SELECT TOP 2 b.main_id,b.ra,b.dec,b.pmra,b.pmdec,b.plx_value,"
             "b.rvz_radvel,b.coo_bibcode,b.pm_bibcode FROM basic AS b "
             "JOIN ident AS i ON b.oid=i.oidref WHERE i.id='" + alias.replace("'", "''") + "'")
    response = client.get(SIMBAD_TAP, params={"REQUEST": "doQuery", "LANG": "ADQL",
                                             "FORMAT": "votable", "QUERY": query}, timeout=30)
    response.raise_for_status()
    table = Table.read(BytesIO(response.content), format="votable")
    if len(table) != 1:
        raise ValueError(f"Expected one unambiguous SIMBAD identity for {target_id}, got {len(table)}")
    row = table[0]
    def number(key: str) -> float | None:
        value = row[key]
        return None if np.ma.is_masked(value) or not np.isfinite(value) else float(value)
    def label(key: str) -> str | None:
        return None if np.ma.is_masked(row[key]) else str(row[key])
    parallax = number("plx_value")
    return Astrometry(reference=Target(target_id=target_id, ra_deg=float(row["ra"]),
        dec_deg=float(row["dec"]), coordinate_source=f"{SIMBAD_TAP}; ICRS epoch J2000"),
        resolved_name=str(row["main_id"]), pm_ra_cosdec_mas_yr=number("pmra"),
        pm_dec_mas_yr=number("pmdec"), parallax_mas=parallax if parallax and parallax > 0 else None,
        radial_velocity_km_s=number("rvz_radvel"), coordinate_bibcode=label("coo_bibcode"),
        proper_motion_bibcode=label("pm_bibcode"), retrieved_at_utc=utc_now(), query=query,
        warnings=["Barycentric astrometry; observer parallax and orbital motion are not modeled"]
        + (["Radial velocity unavailable; perspective acceleration is not constrained"] if number("rvz_radvel") is None else [])
        + (["Epsilon Indi B may be unresolved Ba/Bb; not Epsilon Indi A"] if target_id == "Epsilon Indi B" else []))


def target_at_epoch(astrometry: Astrometry, epoch: Time) -> Target:
    """Propagate measured proper motion; never assume zero for missing values."""
    if astrometry.pm_ra_cosdec_mas_yr is None or astrometry.pm_dec_mas_yr is None:
        raise ValueError("Measured proper motion is required for epoch propagation")
    kwargs = {}
    if astrometry.parallax_mas:
        kwargs["distance"] = (astrometry.parallax_mas * u.mas).to(u.pc, equivalencies=u.parallax())
        if astrometry.radial_velocity_km_s is not None:
            kwargs["radial_velocity"] = astrometry.radial_velocity_km_s * u.km / u.s
    coordinate = SkyCoord(ra=astrometry.reference.ra_deg * u.deg,
        dec=astrometry.reference.dec_deg * u.deg,
        pm_ra_cosdec=astrometry.pm_ra_cosdec_mas_yr * u.mas / u.yr,
        pm_dec=astrometry.pm_dec_mas_yr * u.mas / u.yr,
        obstime=Time(astrometry.reference_epoch_jyear, format="jyear", scale="tt"), **kwargs)
    moved = coordinate.apply_space_motion(new_obstime=epoch)
    return Target(target_id=astrometry.reference.target_id, ra_deg=float(moved.ra.deg),
        dec_deg=float(moved.dec.deg), coordinate_source=(astrometry.reference.coordinate_source
            + f"; proper motion propagated to MJD {epoch.mjd} ({epoch.scale}); observer parallax excluded"))
