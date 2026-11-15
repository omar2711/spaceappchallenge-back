"""Local ephemerides (JPL DE421 + NAIF lunar frame kernels) loaded once, never downloaded at runtime.

Files live in data/ephemeris/ (shipped in the data bundle, see docs/DEPLOY.md):
de421.bsp, moon_pa_de421_1900-2050.bpc, moon_080317.tf, pck00008.tpc.
"""
from functools import lru_cache
from pathlib import Path

from skyfield.api import Loader
from skyfield.planetarylib import PlanetaryConstants

EPHEMERIS_DIR = Path("data/ephemeris")
FILES = ["de421.bsp", "moon_pa_de421_1900-2050.bpc", "moon_080317.tf", "pck00008.tpc"]


class EphemerisMissing(RuntimeError):
    pass


@lru_cache(maxsize=1)
def ephemeris():
    """(timescale, planets, moon_mean_earth_frame). Raises EphemerisMissing instead of downloading."""
    missing = [f for f in FILES if not (EPHEMERIS_DIR / f).exists()]
    if missing:
        raise EphemerisMissing(f"missing ephemeris files in {EPHEMERIS_DIR}: {', '.join(missing)}")
    load = Loader(str(EPHEMERIS_DIR), verbose=False)
    ts = load.timescale(builtin=True)  # built-in Delta-T / leap seconds: no network
    planets = load("de421.bsp")
    pc = PlanetaryConstants()
    pc.read_text(load("moon_080317.tf"))
    pc.read_text(load("pck00008.tpc"))
    pc.read_binary(load("moon_pa_de421_1900-2050.bpc"))
    frame = pc.build_frame_named("MOON_ME_DE421")
    return ts, planets, pc, frame
