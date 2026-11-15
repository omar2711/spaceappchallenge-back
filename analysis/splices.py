"""T4: light SPLICES (SPHEREx target list of ice sources) export for Aladin Lite overlays.

    .venv/Scripts/python -m analysis.splices

SPLICES (Ashby et al. 2023, doi:10.26131/IRSA554) is a TARGET LIST of ~9 million IR-bright point sources
likely to show ice absorption in SPHEREx spectra. It contains positions, photometry and source classes,
NOT measured ice features. We export the sources around our fields (cone search through IRSA Gator, which
answered in seconds while IRSA TAP was timing out) plus an optional all-sky list of bright embedded YSOs.
Output: public-data/catalogs/splices.json
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
from astropy.io import ascii

from analysis.common import PUBLIC_ROOT, load_manifest, target_ids

log = logging.getLogger("analysis.splices")

GATOR = "https://irsa.ipac.caltech.edu/cgi-bin/Gator/nph-query"
COLUMNS = ["source_id", "designation", "ra", "dec", "name", "class_1", "stype_ml", "sel_type", "j", "h", "k",
           "w1", "w2", "w3"]
REGION_RADIUS_ARCMIN = 30.0
OUT = Path("public-data/catalogs/splices.json")
EMBEDDED = {"Class I YSO", "Flat spectrum YSO"}


def gator_cone(ra, dec, radius_arcmin):
    r = requests.get(GATOR, params={"catalog": "splices", "spatial": "cone", "objstr": f"{ra} {dec}",
                                    "radius": str(radius_arcmin * 60), "radunits": "arcsec", "outfmt": "1",
                                    "selcols": ",".join(COLUMNS)}, timeout=300)
    r.raise_for_status()
    return ascii.read(r.text, format="ipac")


def gator_allsky(constraints, max_rows=5000):
    r = requests.get(GATOR, params={"catalog": "splices", "spatial": "NONE", "constraints": constraints,
                                    "outfmt": "1", "outrows": str(max_rows), "selcols": ",".join(COLUMNS)}, timeout=600)
    r.raise_for_status()
    return ascii.read(r.text, format="ipac")


def ice_priority(stype_ml, class_1, sel_type):
    """Our display heuristic (not SPLICES data): 1 = embedded protostar (strongest ices expected),
    2 = other young stellar object, 3 = other (reddened background star, AGB, ...)."""
    if stype_ml in EMBEDDED or sel_type == "EMBED":
        return 1
    if (class_1 or "").startswith("YSO") or "YSO" in (stype_ml or ""):
        return 2
    return 3


def _val(v):
    if np.ma.is_masked(v):
        return None
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else round(float(v), 3)
    if isinstance(v, (np.integer, int)):
        return int(v)
    s = str(v).strip()
    return s or None


def rows_from(table, region):
    out = []
    for r in table:
        d = {c: _val(r[c]) for c in COLUMNS if c in table.colnames}
        out.append({
            "id": d["designation"], "source_id": str(d["source_id"]), "ra": round(d["ra"], 6), "dec": round(d["dec"], 6),
            "name": d.get("name"), "class": d.get("class_1"), "ml_class": d.get("stype_ml"), "selection": d.get("sel_type"),
            "mag": {b: d.get(b) for b in ("j", "h", "k", "w1", "w2", "w3")},
            "ice_priority": ice_priority(d.get("stype_ml"), d.get("class_1"), d.get("sel_type")),
            "regions": [region],
        })
    return out


# Compact table (columns + rows) keeps the file light; magnitudes flattened.
COMPACT_COLUMNS = ["id", "ra", "dec", "name", "class", "ml_class", "selection", "k", "w2", "w3", "ice_priority", "regions"]


def _compact(s, col):
    return s["mag"][col] if col in ("k", "w2", "w3") else s[col]


def our_fields():
    fields = []
    for tid in target_ids():
        m = load_manifest(tid)
        fields.append((tid, m["name"], m["ref_coord"]["ra_deg"], m["ref_coord"]["dec_deg"]))
    presets = PUBLIC_ROOT.parent / "custom" / "presets.json"
    if presets.exists():
        for p in json.loads(presets.read_text(encoding="utf-8"))["presets"]:
            fields.append((p["id"], p["name"], p["ra"], p["dec"]))
    return fields


def build(include_allsky=True):
    sources, regions = {}, []
    for rid, name, ra, dec in our_fields():
        t = gator_cone(ra, dec, REGION_RADIUS_ARCMIN)
        regions.append({"id": rid, "name": name, "ra": ra, "dec": dec, "radius_arcmin": REGION_RADIUS_ARCMIN, "n_sources": len(t)})
        for s in rows_from(t, rid):
            if s["source_id"] in sources:
                sources[s["source_id"]]["regions"].append(rid)
            else:
                sources[s["source_id"]] = s
        log.info("%s: %d SPLICES sources within %.0f'", rid, len(t), REGION_RADIUS_ARCMIN)
    allsky_note = None
    if include_allsky:
        try:
            t = gator_allsky("stype_ml in ('Class I YSO','Flat spectrum YSO') and k < 9")
            n0 = len(sources)
            for s in rows_from(t, "allsky_bright_embedded"):
                sources.setdefault(s["source_id"], s)
            allsky_note = (f"All-sky bright embedded protostars (ML class Class I or flat spectrum, K < 9): "
                           f"{len(t)} sources, {len(sources) - n0} new")
            log.info(allsky_note)
        except Exception as exc:
            allsky_note = f"All-sky list skipped: {str(exc)[:120]}"
            log.warning(allsky_note)
    out = {
        "catalog": "SPLICES (SPHEREx Target List of Ice Sources)",
        "citation": "Ashby et al. 2023, ApJ; dataset doi:10.26131/IRSA554",
        "access": "IRSA Gator cone searches (catalog=splices); full catalog ~8.9 million sources (v8.6, 3.1 GB)",
        "important": ("SPLICES lists sources LIKELY to show ice absorption in SPHEREx spectra; it contains no measured "
                      "ice features. 'ice_priority' is our display heuristic: 1 embedded protostar, 2 other YSO, 3 other."),
        "regions": regions,
        "allsky": allsky_note,
        "n_sources": len(sources),
        "columns": COMPACT_COLUMNS,
        "rows": [[_compact(s, c) for c in COMPACT_COLUMNS]
                 for s in sorted(sources.values(), key=lambda s: (s["ice_priority"], s["ra"]))],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    log.info("%d sources -> %s (%.0f KB)", len(sources), OUT, OUT.stat().st_size / 1024)
    return out


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    build()


if __name__ == "__main__":
    main()
