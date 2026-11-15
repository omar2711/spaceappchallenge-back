"""Lunar Landing Site Navigator: Sun and Earth as seen from a lunar site (Skyfield, DE421 + MOON_ME_DE421).

- Sun/Earth elevation and azimuth on a regular time grid (step configurable).
- Sunlit = any part of the solar disc above the horizon; Earth visible = any part of the Earth above it.
- Windows are found on the grid and refined by linear interpolation of the elevation at the crossings.
- Smooth-sphere horizon: NO local relief (LOLA terrain), so near the poles real horizons (crater rims, massifs)
  can hide the Sun or the Earth even when this model says they are up. Documented limitation.
Validated against JPL Horizons (Apollo 11 site, Sun and Earth, 5 epochs): differences < 0.001 deg.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from b3.ephemeris import ephemeris

SITES_PATH = Path("public-data/moon/sites.json")
SUN_RADIUS_KM = 696_000.0
EARTH_RADIUS_KM = 6_371.0
MAX_DAYS = 30
MIN_STEP_MIN, MAX_STEP_MIN = 5, 360


class SiteNotFound(LookupError):
    pass


@lru_cache(maxsize=1)
def sites():
    return json.loads(SITES_PATH.read_text(encoding="utf-8"))


def get_site(site_id):
    for s in sites()["sites"]:
        if s["id"] == site_id:
            return s
    raise SiteNotFound(f"unknown site '{site_id}'")


def _windows(times_jd, elev, threshold):
    """Intervals where elev > threshold, with crossings linearly interpolated. Returns list of (start_jd, end_jd)."""
    up = elev > threshold
    out = []
    i = 0
    n = len(elev)
    while i < n:
        if not up[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and up[j + 1]:
            j += 1

        def cross(a, b):
            fa, fb = elev[a] - threshold, elev[b] - threshold
            return times_jd[a] + (times_jd[b] - times_jd[a]) * (fa / (fa - fb))
        start = cross(i - 1, i) if i > 0 else None      # None = already up at the start of the range
        end = cross(j, j + 1) if j + 1 < n else None    # None = still up at the end of the range
        out.append((start, end))
        i = j + 1
    return out


def visibility(site_id, start_iso, days=7.0, step_min=30):
    """Sun/Earth visibility from a lunar site. start_iso is UTC (YYYY-MM-DD or YYYY-MM-DDTHH:MM)."""
    site = get_site(site_id)
    days = float(days)
    step_min = int(step_min)
    if not 0 < days <= MAX_DAYS:
        raise ValueError(f"days must be in (0, {MAX_DAYS}]")
    if not MIN_STEP_MIN <= step_min <= MAX_STEP_MIN:
        raise ValueError(f"step_min must be in [{MIN_STEP_MIN}, {MAX_STEP_MIN}]")
    ts, planets, pc, frame = ephemeris()
    from datetime import datetime, timezone
    try:
        t0 = datetime.fromisoformat(start_iso.replace("Z", "")).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("start must be ISO 8601 UTC, e.g. 2026-12-01 or 2026-12-01T06:00") from exc
    n = int(round(days * 24 * 60 / step_min)) + 1
    minutes = np.arange(n) * step_min
    t = ts.utc(t0.year, t0.month, t0.day, t0.hour, t0.minute + minutes)
    place = planets["moon"] + pc.build_latlon_degrees(frame, site["lat"], site["lon"])
    obs = place.at(t)
    s_alt, s_az, s_dist = obs.observe(planets["sun"]).apparent().altaz()
    e_alt, e_az, e_dist = obs.observe(planets["earth"]).apparent().altaz()
    sun_r = np.degrees(np.arcsin(SUN_RADIUS_KM / s_dist.km))
    earth_r = np.degrees(np.arcsin(EARTH_RADIUS_KM / e_dist.km))
    jd = t.tt
    sun_el, earth_el = s_alt.degrees, e_alt.degrees
    sun_win = _windows(jd, sun_el + sun_r, 0.0)
    earth_win = _windows(jd, earth_el + earth_r, 0.0)
    both_mask = (sun_el + sun_r > 0) & (earth_el + earth_r > 0)
    both_win = _windows(jd, np.where(both_mask, 1.0, -1.0), 0.0)

    def iso(jd_tt):
        return None if jd_tt is None else ts.tt_jd(jd_tt).utc_iso()

    def fmt(wins):
        out = []
        for a, b in wins:
            a_ = jd[0] if a is None else a
            b_ = jd[-1] if b is None else b
            out.append({"start": iso(a), "end": iso(b), "hours": round((b_ - a_) * 24, 2),
                        "open_start": a is None, "open_end": b is None})
        return out

    def hours_until(wins, up_now):
        """Hours from the start until the first setting (if up now) or rising (if down now)."""
        if not wins:
            return None
        if up_now:
            end = wins[0][1]
            return None if end is None else round((end - jd[0]) * 24, 2)
        start = wins[0][0]
        return None if start is None else round((start - jd[0]) * 24, 2)

    sun_up0 = bool(sun_el[0] + sun_r[0] > 0)
    earth_up0 = bool(earth_el[0] + earth_r[0] > 0)
    step_h = step_min / 60
    return {
        "site": {k: site[k] for k in ("id", "name", "group", "lat", "lon", "position_type") if k in site},
        "start_utc": iso(jd[0]), "end_utc": iso(jd[-1]), "days": days, "step_min": step_min,
        "summary": {
            "sunlit_hours": round(float(np.sum(sun_el + sun_r > 0)) * step_h, 1),
            "sunlit_fraction": round(float(np.mean(sun_el + sun_r > 0)), 3),
            "earth_visible_hours": round(float(np.sum(earth_el + earth_r > 0)) * step_h, 1),
            "earth_visible_fraction": round(float(np.mean(earth_el + earth_r > 0)), 3),
            "sun_and_earth_hours": round(float(np.sum(both_mask)) * step_h, 1),
            "sun_up_at_start": sun_up0, "earth_up_at_start": earth_up0,
            "hours_to_sunset": hours_until(sun_win, True) if sun_up0 else None,
            "hours_to_sunrise": hours_until(sun_win, False) if not sun_up0 else None,
            "hours_to_earthset": hours_until(earth_win, True) if earth_up0 else None,
            "hours_to_earthrise": hours_until(earth_win, False) if not earth_up0 else None,
            "max_sun_elevation_deg": round(float(sun_el.max()), 3),
            "earth_elevation_range_deg": [round(float(earth_el.min()), 3), round(float(earth_el.max()), 3)],
        },
        "windows": {"sunlit": fmt(sun_win), "earth_visible": fmt(earth_win), "sun_and_earth": fmt(both_win)},
        "series": {
            "time_utc": [ts.tt_jd(x).utc_strftime("%Y-%m-%dT%H:%MZ") for x in jd] if n <= 2000 else None,
            "hours_from_start": np.round((jd - jd[0]) * 24, 3).tolist(),
            "sun_elevation_deg": np.round(sun_el, 3).tolist(), "sun_azimuth_deg": np.round(s_az.degrees, 2).tolist(),
            "earth_elevation_deg": np.round(earth_el, 3).tolist(), "earth_azimuth_deg": np.round(e_az.degrees, 2).tolist(),
        },
        "model": {
            "ephemeris": "JPL DE421 + MOON_ME_DE421 frame (NAIF kernels), Skyfield",
            "horizon": "smooth sphere (no LOLA relief): local terrain can block the Sun/Earth, especially near the poles",
            "sunlit_definition": "any part of the solar disc above the horizon (centre elevation > -apparent radius)",
            "earth_visible_definition": "any part of the Earth above the horizon",
            "validation": "Matches JPL Horizons topocentric elevation/azimuth to < 0.001 deg (Apollo 11 site)",
        },
    }
