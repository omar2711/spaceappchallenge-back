"""Mars walk in Jezero crater (thin version of the Mars challenge), built from official sources only.

    .venv/Scripts/python -m b3.mars            # build public-data/mars/marswalk.json (needs internet)

Sources:
- Route: NASA/JPL Mars 2020 traverse waypoints (MMGIS "Where is Perseverance"), simplified.
- Science stops: sols and sample names from NASA's "Mars Rock Samples" page; positions = rover waypoint at that sol.
- Jezero crater: IAU/USGS Gazetteer of Planetary Nomenclature.
- Hazards: steep segments computed from the official waypoint elevations; plus documented terrain context.
- Layers: NASA Mars Trek WMTS (tiles verified to respond).
Served offline by GET /mars/marswalk (static JSON); the Mars Trek tiles themselves need internet in the browser.
"""
import io
import json
import logging
import math
import re
import zipfile

import requests
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("b3.mars")

OUT = Path("public-data/mars/marswalk.json")
WAYPOINTS_URL = "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json"
SAMPLES_URL = "https://science.nasa.gov/mission/mars-2020-perseverance/mars-rock-samples/"
GAZETTEER_KMZ = "https://asc-planetarynames-data.s3.us-west-2.amazonaws.com/MARS_nomenclature_center_pts.kmz"
TREK = "https://trek.nasa.gov/tiles/Mars/EQ/{layer}/1.0.0//default/default028mm/{{z}}/{{y}}/{{x}}.{ext}"
LAYERS = [
    {"id": "viking_color", "kind": "imagery", "name": "Viking MDIM 2.1 color mosaic (232 m/px)",
     "layer": "Mars_Viking_MDIM21_ClrMosaic_global_232m", "ext": "jpg"},
    {"id": "mola_shaded_relief", "kind": "relief", "name": "MGS MOLA colorized shaded relief (463 m/px)",
     "layer": "Mars_MGS_MOLA_ClrShade_merge_global_463m", "ext": "jpg"},
    {"id": "themis_day_ir", "kind": "thermal", "name": "Mars Odyssey THEMIS day infrared (100 m/px)",
     "layer": "THEMIS_DayIR_ControlledMosaics_100m_v2_oct2018", "ext": "png"},
    {"id": "themis_night_ir", "kind": "temperature", "name": "Mars Odyssey THEMIS night infrared (100 m/px): warm = rocky / high thermal inertia",
     "layer": "THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018", "ext": "png"},
]
# Science stops: (id, title, sample/feature name to look up on the NASA samples page, why it matters for water)
STOPS = [
    ("landing", "Octavia E. Butler Landing", None,
     "Landing site on the floor of an ancient lake (Jezero, ~3.5 billion years ago)."),
    ("rochette", "Rochette (crater floor)", "Rochette",
     "First rock core: igneous rock altered by water after it formed."),
    ("wildcat_ridge", "Wildcat Ridge (delta front)", "Wildcat Ridge",
     "Sedimentary rock laid down where a river entered the lake; organic molecules detected."),
    ("cheyava_falls", "Cheyava Falls / Sapphire Canyon (Neretva Vallis)", "Cheyava Falls",
     "Rock from an ancient river channel with features NASA called a potential biosignature."),
]
STEEP_GRADE = 0.15   # 15 %: steep for a walking route on loose terrain


def _get(url, binary=False):
    # requests uses certifi's up-to-date CA bundle (the local Python store had an expired root).
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Ruta del Agua, Space Apps 2026)"}, timeout=120)
    r.raise_for_status()
    return r.content if binary else r.text


def jezero_from_gazetteer():
    kml = zipfile.ZipFile(io.BytesIO(_get(GAZETTEER_KMZ, binary=True))).read("MARS_nomenclature_center_pts.kml").decode()
    for m in re.findall(r'<Placemark id="[^"]*">(.*?)</Placemark>', kml, re.S):
        if re.search(r'<SimpleData name="clean_name">Jezero</SimpleData>', m):
            g = lambda k: re.search(f'<SimpleData name="{k}">(.*?)</SimpleData>', m, re.S).group(1)  # noqa: E731
            lon = float(g("center_lon"))
            return {"name": "Jezero", "lat": float(g("center_lat")), "lon": lon - 360 if lon > 180 else lon,
                    "diameter_km": round(float(g("diameter")), 1), "source": g("link")}
    raise LookupError("Jezero not found in the IAU Mars gazetteer")


def sample_sols():
    """{feature name: (sol, date, rock type)} from the NASA samples page (first sealed sample of each feature)."""
    text = re.sub(r"<[^>]+>", " ", _get(SAMPLES_URL))
    text = re.sub(r"\s+", " ", text)
    out = {}
    for m in re.finditer(r"Feature Name:\s*(.+?)\s+Sample Type:.*?Sol Sealed:\s*(\d+)\s+Date Sealed:\s*(.+?)\s+Rock Type:\s*(.+?)\s+Sample Height", text):
        name, sol, date, rock = m.group(1).strip(), int(m.group(2)), m.group(3).strip(), m.group(4).strip()
        out.setdefault(name, (sol, date, rock))
    return out


def haversine_m(lat1, lon1, lat2, lon2, r=3_389_500.0):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def build():
    wps = [f["properties"] for f in json.loads(_get(WAYPOINTS_URL))["features"]]
    wps = [w for w in wps if w.get("final") == "y" or w.get("Note") == "First localization!"]
    wps.sort(key=lambda w: (w["sol"], w["dist_total_m"]))
    samples = sample_sols()

    stops = []
    for sid, title, feature, why in STOPS:
        if feature is None:
            sol, date, rock = wps[0]["sol"], "2021-02-18 (landing)", None
        else:
            sol, date, rock = samples[feature]
        wp = [w for w in wps if w["sol"] <= sol][-1]
        stops.append({"id": sid, "title": title, "sol": sol, "date": date, "rock_type": rock,
                      "lat": round(wp["lat"], 6), "lon": round(wp["lon"], 6), "elevation_m": round(wp["elev_geoid"], 1),
                      "odometry_km": round(wp["dist_total_m"] / 1000, 2), "why_water": why,
                      "position_source": f"rover waypoint at sol {wp['sol']} (site {wp['site']}, drive {wp['drive']})"})
    last_sol = stops[-1]["sol"]
    route_wps = [w for w in wps if w["sol"] <= last_sol]

    # Simplify the route (one point every >= 150 m) and keep elevation for the profile.
    route = [route_wps[0]]
    for w in route_wps[1:]:
        if haversine_m(route[-1]["lat"], route[-1]["lon"], w["lat"], w["lon"]) >= 150:
            route.append(w)
    if route[-1] is not route_wps[-1]:
        route.append(route_wps[-1])
    hazards = []
    for a, b in zip(route_wps, route_wps[1:]):
        d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
        if d >= 20 and abs(b["elev_geoid"] - a["elev_geoid"]) / d >= STEEP_GRADE:
            hazards.append({"type": "steep_slope", "lat": round(b["lat"], 6), "lon": round(b["lon"], 6), "sol": b["sol"],
                            "grade_percent": round(100 * (b["elev_geoid"] - a["elev_geoid"]) / d, 1),
                            "segment_m": round(d, 1), "source": "computed from official waypoint elevations"})
    hazards.sort(key=lambda h: -abs(h["grade_percent"]))
    jezero = jezero_from_gazetteer()
    out = {
        "title": "Ruta del Agua en Marte: caminata por el cráter Jezero siguiendo a Perseverance",
        "summary": ("Jezero held a lake ~3.5 billion years ago, fed by a river that built a delta. The walk follows "
                    "NASA's Perseverance rover from its landing site across the crater floor to the delta front and an "
                    "ancient river channel, stopping where water left its mark in the rocks."),
        "crater": jezero,
        "frame": "Mars planetocentric, lon east positive (-180..180), elevations relative to the Mars geoid (m)",
        "route": {"n_points": len(route), "length_km": round(route_wps[-1]["dist_total_m"] / 1000, 2),
                  "sols": [route_wps[0]["sol"], route_wps[-1]["sol"]],
                  "points": [{"lat": round(w["lat"], 6), "lon": round(w["lon"], 6), "elevation_m": round(w["elev_geoid"], 1),
                              "sol": w["sol"], "odometry_km": round(w["dist_total_m"] / 1000, 3)} for w in route],
                  "source": WAYPOINTS_URL, "simplification": "one waypoint every >= 150 m"},
        "stops": stops,
        "hazards": {
            "steep_segments": hazards[:15],
            "terrain_context": [
                {"type": "sand", "text": "Séítah ('amidst the sand' in Navajo): ripples and sand between the landing site and the delta; Perseverance drove around it."},
                {"type": "slopes_boulders", "text": "Delta front and crater rim: steep, boulder-strewn slopes (see steep_segments)."},
                {"type": "environment", "text": "Thin CO2 atmosphere, cold nights below -80 C, dust storms and surface radiation."},
            ],
            "steep_threshold_percent": STEEP_GRADE * 100,
        },
        "layers": [{**{k: v for k, v in L.items() if k not in ("layer", "ext")},
                    "url_template": TREK.format(layer=L["layer"], ext=L["ext"]),
                    "tile_scheme": "WMTS geographic (EPSG:4326-like), level 0 = 2x1 tiles of 256 px; {z}/{y}/{x} = TileMatrix/TileRow/TileCol",
                    "verified": None} for L in LAYERS],
        "sources": {"waypoints": WAYPOINTS_URL, "samples": SAMPLES_URL, "gazetteer": GAZETTEER_KMZ,
                    "mars_trek": "https://trek.nasa.gov/mars/"},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    # Verify one tile per layer over Jezero (zoom 6).
    z = 6
    col = int((jezero["lon"] + 180) / 360 * 2 ** (z + 1))
    row = int((90 - jezero["lat"]) / 180 * 2 ** z)
    for L in out["layers"]:
        url = L["url_template"].replace("{z}", str(z)).replace("{y}", str(row)).replace("{x}", str(col))
        try:
            ok = len(_get(url, binary=True)) > 1000
        except Exception:
            ok = False
        L["verified"] = {"ok": ok, "test_tile": url, "checked_at": out["generated_at"]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    log.info("marswalk: %d route points, %d stops, %d steep segments, layers ok: %s -> %s", len(route), len(stops),
             len(hazards), [L["verified"]["ok"] for L in out["layers"]], OUT)
    return out


def load():
    return json.loads(OUT.read_text(encoding="utf-8"))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    build()


if __name__ == "__main__":
    main()
