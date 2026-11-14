"""Phase 1 exploration: Barnard's Star in SPHEREx (SIA metadata + one cutout).

Run from the repo root:
    .venv/Scripts/python -m pipeline.explore_barnard
"""
import logging
import time
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy.coordinates import Distance, SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from astroquery.ipac.irsa import Irsa

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("explore")

RAW_DIR = Path("data/raw/barnard_check")
COLLECTIONS = ["spherex_dr1", "spherex_qr3"]
SEARCH_RADIUS = 10 * u.arcmin
CUTOUT_SIZE_DEG = 4 / 60
PIXEL_SCALE = 6.15  # arcsec, nominal
EPOCH_GAP_DAYS = 60
BARNARD_GAIA_DR3 = 4472832130942575872


def retry(fn, tries=4, wait=5):
    for i in range(tries):
        try:
            return fn()
        except Exception as exc:  # IRSA/SIMBAD timeouts are transient
            log.warning("attempt %d/%d failed: %s", i + 1, tries, exc)
            if i == tries - 1:
                raise
            time.sleep(wait * (i + 1))


def resolve_target(gaia_source_id):
    """Gaia DR3 astrometry (epoch 2016.0). SIMBAD TAP returned 404 on 2026-11-14, so Gaia is primary."""
    from astroquery.gaia import Gaia
    query = (
        "SELECT source_id, ra, dec, pmra, pmdec, parallax, radial_velocity, ref_epoch "
        f"FROM gaiadr3.gaia_source WHERE source_id = {gaia_source_id}"
    )
    row = retry(lambda: Gaia.launch_job(query).get_results())[0]
    rv = row["radial_velocity"]
    coord = SkyCoord(
        ra=row["ra"] * u.deg, dec=row["dec"] * u.deg,
        pm_ra_cosdec=row["pmra"] * u.mas / u.yr, pm_dec=row["pmdec"] * u.mas / u.yr,
        distance=Distance(parallax=row["parallax"] * u.mas),
        radial_velocity=(0.0 if np.ma.is_masked(rv) else float(rv)) * u.km / u.s,
        obstime=Time(float(row["ref_epoch"]), format="jyear"),
    )
    return coord, row


def group_epochs(times_mjd):
    """Assign an epoch label to each time: a new epoch starts after a gap > EPOCH_GAP_DAYS."""
    order = np.argsort(times_mjd)
    labels = np.empty(len(times_mjd), dtype=object)
    epoch, prev = 1, None
    for idx in order:
        t = times_mjd[idx]
        if prev is not None and t - prev > EPOCH_GAP_DAYS:
            epoch += 1
        labels[idx] = f"S{epoch}"
        prev = t
    return labels


def cached_cutout(url, coord, name):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / name
    if not path.exists():
        cut_url = f"{url}?center={coord.ra.deg},{coord.dec.deg}d&size={CUTOUT_SIZE_DEG}"
        log.info("downloading cutout %s", cut_url)
        def fetch():
            with fits.open(cut_url) as hdul:
                hdul.writeto(path, overwrite=True)
        retry(fetch)
    return path


def main():
    log.info("SIA collections: %s", list(Irsa.list_collections(servicetype="SIA", filter="spherex")["collection"]))

    c2000, row = resolve_target(BARNARD_GAIA_DR3)
    print("\n=== Barnard (Gaia DR3, epoch 2016.0) ===")
    print(f"RA {row['ra']:.6f}  Dec {row['dec']:.6f}  pmra {row['pmra']:.1f} pmdec {row['pmdec']:.1f} mas/yr  plx {row['parallax']:.2f} mas  rv {row['radial_velocity']} km/s")
    for label, date in [("2025-05", "2025-05-15"), ("2026-11", "2026-11-14")]:
        c = c2000.apply_space_motion(new_obstime=Time(date))
        sep = c.separation(c2000.apply_space_motion(new_obstime=Time("2025-05-15")))
        print(f"{label}: RA {c.ra.deg:.6f} Dec {c.dec.deg:.6f}  (offset from 2016.0 {c.separation(SkyCoord(c2000.ra, c2000.dec)).arcmin:.2f}'; from 2025-05 {sep.arcsec:.2f}\" = {sep.arcsec / PIXEL_SCALE:.2f} px)")

    c_now = c2000.apply_space_motion(new_obstime=Time("2025-11-01"))
    search = SkyCoord(c_now.ra, c_now.dec)
    res = retry(lambda: Irsa.query_sia(pos=(search, SEARCH_RADIUS), collection=COLLECTIONS))
    print(f"\n=== SIA: {len(res)} images within {SEARCH_RADIUS} ===")
    print("columns:", res.colnames)

    t_min = np.asarray(res["t_min"], dtype=float)
    res["epoch"] = group_epochs(t_min)
    print(f"date range: {Time(t_min.min(), format='mjd').iso} -> {Time(t_min.max(), format='mjd').iso}")
    for col in ["energy_bandpassname", "obs_collection", "dataproduct_subtype", "instrument_name", "facility_name"]:
        if col in res.colnames:
            vals, counts = np.unique(np.asarray(res[col]).astype(str), return_counts=True)
            print(f"{col}: {dict(zip(vals, counts.tolist()))}")

    print("\n=== epochs x detector (n images) ===")
    for ep in sorted(set(res["epoch"]), key=lambda s: int(s[1:])):
        sel = res["epoch"] == ep
        tt = t_min[sel]
        dets, counts = np.unique(np.asarray(res["energy_bandpassname"][sel]).astype(str), return_counts=True)
        print(f"{ep}: {Time(tt.min(), format='mjd').iso[:10]} -> {Time(tt.max(), format='mjd').iso[:10]}  {dict(zip(dets, counts.tolist()))}")

    print("\nsample rows:")
    show = [c for c in ["obs_id", "energy_bandpassname", "t_min", "t_exptime", "em_min", "em_max", "access_url"] if c in res.colnames]
    print(res[show][:3])

    # Open one cutout: first image in the earliest epoch whose footprint contains the target.
    first = res[np.argsort(t_min)][0]
    t_obs = Time(float(first["t_min"]), format="mjd")
    c_obs = c2000.apply_space_motion(new_obstime=t_obs)
    path = cached_cutout(str(first["access_url"]), c_obs, "explore_first.fits")
    print(f"\n=== cutout {path} ===")
    with fits.open(path) as hdul:
        hdul.info()
        img_h = hdul["IMAGE"].header
        print("\nPRIMARY keys:", {k: hdul[0].header.get(k) for k in ["VERSION", "DETECTOR", "DATE-OBS", "MJD-OBS", "OBSID"] if k in hdul[0].header})
        keys = ["DETECTOR", "DATE", "DATE-OBS", "DATE-END", "MJD-OBS", "MJD-AVG", "BUNIT", "CTYPE1", "CTYPE2", "CRVAL1", "CRVAL2", "CDELT1", "CD1_1", "PC1_1", "NAXIS1", "NAXIS2", "CTYPE1W", "CTYPE2W"]
        print("IMAGE keys:", {k: img_h.get(k) for k in keys if k in img_h})
        flags_h = hdul["FLAGS"].header
        print("\nFLAGS bits:")
        for key in flags_h["MSKN*"]:
            bit = key[4:]
            print(f"  {int(bit):2d} {flags_h[key]:<14} {flags_h.get('MSKD' + bit, '')}")
        wcs = WCS(img_h)
        x, y = wcs.world_to_pixel(c_obs)
        swcs = WCS(img_h, fobj=hdul, key="W")
        swcs.sip = None
        wl, bw = swcs.pixel_to_world(x, y)
        ny, nx = hdul["IMAGE"].data.shape
        wl_edges = [swcs.pixel_to_world(px, py)[0].to(u.um).value for px, py in [(0, 0), (nx - 1, ny - 1)]]
        print(f"\ntarget pixel ({x:.1f}, {y:.1f}) of {nx}x{ny}; wavelength {wl.to(u.um):.4f}, bandwidth {bw.to(u.um):.4f}")
        print(f"wavelength at cutout corners: {wl_edges[0]:.4f} / {wl_edges[1]:.4f} um")
        scale = np.abs(wcs.proj_plane_pixel_scales()[0].to(u.arcsec))
        print(f"pixel scale {scale:.3f}")


if __name__ == "__main__":
    main()
