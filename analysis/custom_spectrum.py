"""Spectrum at arbitrary coordinates (also the base for T5's API function).

    .venv/Scripts/python -m analysis.custom_spectrum --ra 83.80880 --dec -5.37298 --label "BN/KL" \
        --field c2d9e7410cce7

Downloads (or reuses) up to max_per_group cutouts per (epoch x detector) around the position, measures forced
photometry on every exposure and bins it into per-epoch + combined spectra with band measurements.
With --field, the result is written as the analysis.json of that custom field (public-data/custom/<field>/),
with target_px giving the position inside that field.
"""
import argparse
import json
import logging
from datetime import datetime, timezone

import jsonschema
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS

from analysis.common import SCHEMA_PATH
from analysis.photometry import CACHE_ROOT, spec_photometry
from analysis.spectra import REFERENCE_BANDS, spectra_from_photometry
from pipeline.fetch import fetch_spec
from pipeline.targets import PUBLIC_ROOT, custom_spec

log = logging.getLogger("analysis.custom_spectrum")


def spectrum_for_coords(ra, dec, label=None, max_per_group=10, fov_arcmin=2.0, workers=4, kind=None):
    """Per-epoch + combined spectra at (ra, dec). Raw cutouts are kept in data/raw/custom/<id> as a cache."""
    spec = custom_spec(ra, dec, fov_arcmin, max_per_group)
    fetch_spec(spec, workers=workers, max_per_group=max_per_group)
    phot = spec_photometry(spec, CACHE_ROOT / "custom" / spec.id / "photometry.ecsv")
    position = {"ra_deg": spec.astrometry["ra"], "dec_deg": spec.astrometry["dec"]}
    if label:
        position["label"] = label
    return spec, spectra_from_photometry(phot, label=label, position=position, kind=kind)


def target_px_in_field(field_manifest, ra, dec):
    g = field_manifest["grid_wcs"]
    w = WCS(naxis=2)
    w.wcs.ctype = [g["CTYPE1"], g["CTYPE2"]]
    w.wcs.crval = [g["CRVAL1"], g["CRVAL2"]]
    w.wcs.crpix = [g["CRPIX1"], g["CRPIX2"]]
    w.wcs.cdelt = [g["CDELT1"], g["CDELT2"]]
    x, y = w.world_to_pixel(SkyCoord(ra, dec, unit="deg"))
    return [round(float(x), 3), round(float(g["NAXIS2"] - 1 - y), 3)]  # web convention, as manifest target_px


def write_field_analysis(field_id, spectra, notes):
    field_dir = PUBLIC_ROOT / "custom" / field_id
    manifest = json.loads((field_dir / "manifest.json").read_text(encoding="utf-8"))
    for s in spectra:
        p = s.get("position")
        if p:
            p["target_px"] = target_px_in_field(manifest, p["ra_deg"], p["dec_deg"])
    out = {"target_id": field_id, "difference_images": [], "deep_images": [], "light_curves": [],
           "spectra": spectra, "reference_bands": REFERENCE_BANDS, "notes": notes,
           "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    jsonschema.validate(out, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    path = field_dir / "analysis.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return path


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("astropy").setLevel(logging.ERROR)
    p = argparse.ArgumentParser()
    p.add_argument("--ra", type=float, required=True)
    p.add_argument("--dec", type=float, required=True)
    p.add_argument("--label")
    p.add_argument("--max-per-group", type=int, default=10)
    p.add_argument("--field", help="custom field id to attach the spectrum to (writes its analysis.json)")
    a = p.parse_args()
    spec, spectra = spectrum_for_coords(a.ra, a.dec, a.label, a.max_per_group)
    c = spectra[-1]
    for b in c["band_measurements"]:
        if b.get("value") is not None:
            log.info("%-13s %-5s %+.3f ± %.3f (%+.1f sigma)", b["name"], b["type"], b["value"], b["err"],
                     b["absorption_sigma"] or 0)
    if a.field:
        notes = (f"Forced spectrophotometry at {a.label or 'the given position'} "
                 f"(RA {a.ra:.5f}, Dec {a.dec:+.5f}) from {c['n_exposures']} exposures "
                 f"(up to {a.max_per_group} per epoch x detector). Aperture r = 12\" with a 31-49\" annulus: in a "
                 "bright nebula the local background is structured, so absolute fluxes carry extra uncertainty. "
                 "Saturated points are lower limits.")
        log.info("written %s", write_field_analysis(a.field, spectra, notes))


if __name__ == "__main__":
    main()
