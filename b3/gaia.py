"""Gaia DR3 sources in each field, propagated to the mid-date of every SPHEREx epoch (for motion arrows).

    .venv/Scripts/python -m b3.gaia            # build public-data/catalogs/gaia/<field>.json (needs internet)

Served offline by GET /gaia?field=... (static JSON). Positions are given on the sky (ICRS) and in WebP pixel
coordinates of the field's frames (origin top-left, same convention as manifest target_px).
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.time import Time
from astropy.wcs import WCS

log = logging.getLogger("b3.gaia")

OUT_DIR = Path("public-data/catalogs/gaia")
G_LIMIT = 20.0
MIN_PM_ARROW = 20.0   # mas/yr: below this the motion over the mission is < 0.02 px, arrows are not meaningful


def fields():
    """(field id, manifest path) for the 5 targets and the demo presets."""
    out = []
    index = json.loads(Path("public-data/targets/index.json").read_text(encoding="utf-8"))
    for t in index["targets"]:
        out.append((t["target_id"], Path("public-data/targets") / t["manifest"]))
    presets = json.loads(Path("public-data/custom/presets.json").read_text(encoding="utf-8"))["presets"]
    for p in presets:
        out.append((p["id"], Path("public-data") / p["manifest"]))
    return out


def grid_wcs(manifest):
    g = manifest["grid_wcs"]
    w = WCS(naxis=2)
    w.wcs.ctype = [g["CTYPE1"], g["CTYPE2"]]
    w.wcs.crval = [g["CRVAL1"], g["CRVAL2"]]
    w.wcs.crpix = [g["CRPIX1"], g["CRPIX2"]]
    w.wcs.cdelt = [g["CDELT1"], g["CDELT2"]]
    return w, g["NAXIS2"]


def query_gaia(ra, dec, radius_deg):
    from astroquery.gaia import Gaia
    q = (f"SELECT source_id, ra, dec, pmra, pmdec, parallax, phot_g_mean_mag, ref_epoch FROM gaiadr3.gaia_source "
         f"WHERE 1=CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra}, {dec}, {radius_deg})) "
         f"AND phot_g_mean_mag < {G_LIMIT}")
    return Gaia.launch_job(q).get_results()


def build_field(fid, manifest_path):
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    w, ny = grid_wcs(m)
    ra0, dec0 = m["grid_wcs"]["CRVAL1"], m["grid_wcs"]["CRVAL2"]
    radius = m["fov_arcmin"] / 60 * 0.75  # covers the corners of the square field
    t = query_gaia(ra0, dec0, radius)
    epochs = [(e["id"], e["date_mid"]) for e in m["epochs"]]
    sources = []
    for r in t:
        pmra = None if np.ma.is_masked(r["pmra"]) else float(r["pmra"])
        pmdec = None if np.ma.is_masked(r["pmdec"]) else float(r["pmdec"])
        ra, dec = float(r["ra"]), float(r["dec"])
        pos = {}
        for eid, date in epochs:
            dt_yr = (Time(date).jyear - float(r["ref_epoch"])) if pmra is not None else 0.0
            c = SkyCoord(ra, dec, unit="deg")
            if pmra is not None:  # pmra already includes cos(dec): an on-sky offset
                c = c.spherical_offsets_by(pmra * dt_yr * u.mas, pmdec * dt_yr * u.mas)
            x, y = w.world_to_pixel(c)
            pos[eid] = {"ra": round(c.ra.deg, 7), "dec": round(c.dec.deg, 7),
                        "px": [round(float(x), 3), round(float(ny - 1 - y), 3)]}
        pm_tot = None if pmra is None else float(np.hypot(pmra, pmdec))
        sources.append({
            "source_id": str(r["source_id"]), "ra": round(ra, 7), "dec": round(dec, 7), "ref_epoch": float(r["ref_epoch"]),
            "pmra": None if pmra is None else round(pmra, 3), "pmdec": None if pmdec is None else round(pmdec, 3),
            "parallax": None if np.ma.is_masked(r["parallax"]) else round(float(r["parallax"]), 3),
            "g_mag": round(float(r["phot_g_mean_mag"]), 3), "pm_total_mas_yr": None if pm_tot is None else round(pm_tot, 2),
            "arrow": bool(pm_tot is not None and pm_tot >= MIN_PM_ARROW), "epochs": pos})
    sources.sort(key=lambda s: s["g_mag"])
    out = {
        "field": fid, "catalog": "Gaia DR3 (ESA/Gaia/DPAC), gaiadr3.gaia_source", "g_limit": G_LIMIT,
        "center": {"ra": ra0, "dec": dec0}, "radius_deg": round(radius, 5), "image_size_px": m["image_size_px"],
        "epochs": [{"id": e, "date_mid": d} for e, d in epochs],
        "notes": ("Positions propagated from ref_epoch (2016.0) with proper motion only (no parallax/radial "
                  "velocity). px = WebP pixel coordinates of this field's frames (origin top-left). 'arrow' marks "
                  f"sources with total proper motion >= {MIN_PM_ARROW} mas/yr."),
        "n_sources": len(sources), "sources": sources,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{fid}.json"
    path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    log.info("%s: %d Gaia sources (%d with arrows) -> %s", fid, len(sources), sum(s["arrow"] for s in sources), path)
    return out


def load_field(fid):
    path = OUT_DIR / f"{fid}.json"
    if not path.exists():
        raise LookupError(f"no Gaia catalogue for field '{fid}'")
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for fid, mpath in fields():
        build_field(fid, mpath)


if __name__ == "__main__":
    main()
