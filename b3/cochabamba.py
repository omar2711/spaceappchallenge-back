"""Is it visible from Cochabamba tonight? Altitude curve, rise/set, culmination, best time, observability.

Site: Cochabamba, Bolivia, 17.38833 S, 66.15972 W (Wikipedia), ~2,550 m (sources give 2,537-2,577 m; the
difference changes altitudes by < 0.01 deg). Local time = UTC-4 (Bolivia has no daylight saving time).
"Night" = Sun below -12 deg (nautical twilight); observable = altitude > 20 deg at some time during the night.
Geometric altitude (no atmospheric refraction, which adds ~0.5 deg at the horizon). Offline: local DE421.
"""
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone

import numpy as np
from skyfield.api import Star, wgs84
from skyfield.almanac import fraction_illuminated

from b3.ephemeris import ephemeris

SITE = {"name": "Cochabamba, Bolivia", "lat": -17.38833, "lon": -66.15972, "elevation_m": 2550,
        "utc_offset_hours": -4,
        "source": "Wikipedia (17°23'18\"S 66°09'35\"W); elevation ~2,550 m (2,537-2,577 m across GeoNames/WorldAtlas)"}
LOCAL = timezone(timedelta(hours=SITE["utc_offset_hours"]))
NIGHT_SUN_ALT = -12.0
MIN_ALT = 20.0
STEP_MIN = 5


def _crossings(minutes, alt, level):
    """Interpolated times (minutes) where alt crosses level, with direction (+1 rising, -1 setting)."""
    out = []
    for i in range(len(alt) - 1):
        a, b = alt[i] - level, alt[i + 1] - level
        if a == 0 or a * b < 0:
            f = a / (a - b) if a != b else 0
            out.append((minutes[i] + f * (minutes[i + 1] - minutes[i]), 1 if b > a else -1))
    return out


def visibility(ra_deg, dec_deg, date_str=None):
    """Night starting on the local date `date_str` (YYYY-MM-DD, default today in Cochabamba): local noon to noon."""
    ra_deg, dec_deg = float(ra_deg) % 360, float(dec_deg)
    if not -90 <= dec_deg <= 90:
        raise ValueError("dec must be in [-90, 90]")
    if date_str:
        try:
            d = date_cls.fromisoformat(date_str)
        except ValueError as exc:
            raise ValueError("date must be YYYY-MM-DD") from exc
    else:
        d = datetime.now(LOCAL).date()
    ts, planets, _, _ = ephemeris()
    start_local = datetime(d.year, d.month, d.day, 12, 0, tzinfo=LOCAL)
    start_utc = start_local.astimezone(timezone.utc)
    minutes = np.arange(0, 24 * 60 + 1, STEP_MIN)
    t = ts.utc(start_utc.year, start_utc.month, start_utc.day, start_utc.hour, start_utc.minute + minutes)
    earth = planets["earth"]
    observer = earth + wgs84.latlon(SITE["lat"], SITE["lon"], elevation_m=SITE["elevation_m"])
    star = Star(ra_hours=ra_deg / 15, dec_degrees=dec_deg)
    alt, az, _ = observer.at(t).observe(star).apparent().altaz()
    s_alt, _, _ = observer.at(t).observe(planets["sun"]).apparent().altaz()
    m_alt, _, _ = observer.at(t).observe(planets["moon"]).apparent().altaz()
    alt, az, s_alt, m_alt = alt.degrees, az.degrees, s_alt.degrees, m_alt.degrees

    def local(minute):
        return None if minute is None else (start_local + timedelta(minutes=float(minute))).strftime("%Y-%m-%dT%H:%M")

    night = s_alt < NIGHT_SUN_ALT
    sun_cross = _crossings(minutes, s_alt, NIGHT_SUN_ALT)
    night_start = next((m for m, s in sun_cross if s < 0), None)
    night_end = next((m for m, s in sun_cross if s > 0), None)
    sunset = next((m for m, s in _crossings(minutes, s_alt, 0.0) if s < 0), None)
    sunrise = next((m for m, s in _crossings(minutes, s_alt, 0.0) if s > 0), None)
    rises = [m for m, s in _crossings(minutes, alt, 0.0) if s > 0]
    sets = [m for m, s in _crossings(minutes, alt, 0.0) if s < 0]
    i_max = int(np.argmax(alt))
    good = night & (alt > MIN_ALT)
    best = int(np.argmax(np.where(night, alt, -999))) if night.any() else None
    moon_illum = float(fraction_illuminated(planets, "moon", ts.utc(start_utc + timedelta(hours=12))))
    return {
        "site": SITE, "target": {"ra_deg": round(ra_deg, 6), "dec_deg": round(dec_deg, 6)},
        "date_local": d.isoformat(), "window_local": [local(0), local(minutes[-1])],
        "sun": {"sunset": local(sunset), "sunrise": local(sunrise), "night_start": local(night_start),
                "night_end": local(night_end), "night_definition": f"Sun below {NIGHT_SUN_ALT} deg"},
        "target_events": {
            "rise": local(rises[0]) if rises else None, "set": local(sets[0]) if sets else None,
            "culmination": local(minutes[i_max]), "culmination_alt_deg": round(float(alt[i_max]), 2),
            "always_up": bool(alt.min() > 0), "never_up": bool(alt.max() < 0),
        },
        "best_time": None if best is None else {"time": local(minutes[best]), "alt_deg": round(float(alt[best]), 2),
                                                "az_deg": round(float(az[best]), 1),
                                                "moon_alt_deg": round(float(m_alt[best]), 1)},
        "observable": bool(good.any()),
        "observable_hours": round(float(good.sum()) * STEP_MIN / 60, 2),
        "criterion": f"altitude > {MIN_ALT} deg while the Sun is below {NIGHT_SUN_ALT} deg",
        "moon_illuminated_fraction": round(moon_illum, 3),
        "curve": {"step_min": STEP_MIN, "time_local": [local(m) for m in minutes],
                  "alt_deg": np.round(alt, 2).tolist(), "az_deg": np.round(az, 1).tolist(),
                  "sun_alt_deg": np.round(s_alt, 2).tolist()},
        "notes": "Geometric altitude (no refraction, ~0.5 deg at the horizon). Local time UTC-4.",
    }
