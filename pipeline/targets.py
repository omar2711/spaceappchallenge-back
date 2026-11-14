"""Target configuration (pipeline/targets.yaml) and offline position propagation."""
from functools import lru_cache
from pathlib import Path

import astropy.units as u
import yaml
from astropy.coordinates import Distance, SkyCoord
from astropy.time import Time

TARGETS_PATH = Path(__file__).with_name("targets.yaml")


@lru_cache(maxsize=None)
def load_targets():
    return yaml.safe_load(TARGETS_PATH.read_text(encoding="utf-8"))


def get_target(target_id):
    targets = load_targets()
    if target_id not in targets:
        raise SystemExit(f"unknown target '{target_id}'; known: {', '.join(targets)}")
    return targets[target_id]


def reference_coord(target_id):
    """SkyCoord with space motion at the catalogue epoch. Use .apply_space_motion(new_obstime=...) to move it.

    Annual parallax displacement is not applied (< 0.6" for every target, i.e. < 0.1 px).
    """
    a = get_target(target_id)["astrometry"]
    return SkyCoord(
        ra=a["ra"] * u.deg, dec=a["dec"] * u.deg,
        pm_ra_cosdec=a["pmra"] * u.mas / u.yr, pm_dec=a["pmdec"] * u.mas / u.yr,
        distance=Distance(parallax=a["plx"] * u.mas),
        radial_velocity=a.get("rv", 0.0) * u.km / u.s,
        obstime=Time(a["epoch"], format="jyear"),
    )


def position_at(target_id, time):
    c = reference_coord(target_id).apply_space_motion(new_obstime=Time(time))
    return SkyCoord(c.ra, c.dec)
