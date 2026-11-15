"""Conservative forced-aperture measurements on calibrated SPHEREx cutouts."""

from pathlib import Path
from typing import Literal, cast
import hashlib

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

from .fits_io import read_image
from .observation_models import ApertureConfig, CachedCutout, Measurement, Target


def _solid_angles(wcs, x, y):
    """Spherical quadrilateral areas from four WCS pixel corners, in steradians."""
    vectors = [np.moveaxis(wcs.pixel_to_world(x + dx, y + dy).cartesian.xyz.value, 0, -1)
               for dx, dy in [(-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5)]]
    def triangle(a, b, c):
        numerator = np.abs(np.sum(a * np.cross(b, c), axis=-1))
        denominator = 1 + np.sum(a*b, axis=-1) + np.sum(b*c, axis=-1) + np.sum(c*a, axis=-1)
        return 2 * np.arctan2(numerator, denominator)
    return triangle(*vectors[:3]) + triangle(vectors[0], vectors[2], vectors[3])


def aperture_measurement(cutout: CachedCutout, root: Path, target: Target,
                         config: ApertureConfig) -> Measurement:
    """Aperture minus local annular mean; independent pixel variances propagated.

    No aperture/colour/PSF correction or AB magnitude is assumed. Masked source
    pixels and clipped apertures are rejected rather than filled or rescaled.
    """
    image, header = read_image(cutout.asset, root)
    path = (root / cutout.asset.path).resolve(strict=True)
    if hashlib.sha256(path.read_bytes()).hexdigest() != cutout.sha256:
        raise ValueError("Cutout checksum mismatch")
    with fits.open(path, memmap=False) as hdus:
        variance_hdu, flags_hdu = hdus["VARIANCE"], hdus["FLAGS"]
        variance = np.asarray(variance_hdu.data, dtype=float)
        flags = np.asarray(flags_hdu.data)
        flag_labels = {int(key[4:]): str(flags_hdu.header[key]) for key in flags_hdu.header
                       if key.startswith("MSKN") and key[4:].isdigit()}
        if variance.shape != image.shape or flags.shape != image.shape:
            raise ValueError("IMAGE/VARIANCE/FLAGS shapes differ")
        if not np.issubdtype(flags.dtype, np.integer):
            raise ValueError("FLAGS must contain integer bit fields")
        image_unit = u.Unit(header["BUNIT"])
        surface_factor = image_unit.to(u.MJy / u.sr)
        variance *= u.Unit(variance_hdu.header["BUNIT"]).to(image_unit ** 2)
        image *= surface_factor
        variance *= surface_factor ** 2
        wcs = WCS(header)
        if not wcs.has_celestial:
            raise ValueError("Celestial WCS required")
        coordinate = SkyCoord(target.ra_deg, target.dec_deg, unit="deg")
        x, y = (float(v) for v in wcs.world_to_pixel(coordinate))
        if not (0 <= x < image.shape[1] and 0 <= y < image.shape[0]):
            raise ValueError("Target lies outside cutout")
        spectral = WCS(header, fobj=hdus, key="W")
        spectral.sip = None  # documented SPHEREx alternative-WCS convention
        wavelength, bandwidth = spectral.pixel_to_world(x, y)
        wavelength_um = float(wavelength.to_value(u.um))
        bandwidth_um = float(bandwidth.to_value(u.um))
        version = str(hdus[0].header.get("VERSION", ""))
        if not version or "DETECTOR" not in header:
            raise ValueError("Missing product VERSION or DETECTOR")
        if cutout.observation.band and cutout.observation.band != f"SPHEREx-D{header['DETECTOR']}":
            raise ValueError("FITS detector disagrees with SIA band")

        # Radius in equivalent local pixels; the actual aperture is circular on sky.
        angular_pixel = np.sqrt(_solid_angles(wcs, x, y))
        outer = config.annulus_outer_px * angular_pixel
        edges_x = np.concatenate([np.arange(image.shape[1]), np.arange(image.shape[1]),
                                  np.zeros(image.shape[0]), np.full(image.shape[0], image.shape[1]-1)])
        edges_y = np.concatenate([np.zeros(image.shape[1]), np.full(image.shape[1], image.shape[0]-1),
                                  np.arange(image.shape[0]), np.arange(image.shape[0])])
        if np.min(wcs.pixel_to_world(edges_x, edges_y).separation(coordinate).rad) <= outer:
            raise ValueError("Target annulus is clipped or outside cutout")

        mjd = None
        scale: Literal["utc", "tt", "tdb"] | None = None
        if "TIMESYS" in header:
            candidate = str(header["TIMESYS"]).lower()
            if candidate in ("utc", "tt", "tdb"):
                scale = cast(Literal["utc", "tt", "tdb"], candidate)
        if "MJD-OBS" in header:
            mjd = float(header["MJD-OBS"])
        elif cutout.observation.mjd_start is not None:
            mjd = cutout.observation.mjd_start
            scale = cutout.observation.time_scale

    yy, xx = np.indices(image.shape)
    weights = np.zeros(image.shape, dtype=float)
    for sy in (np.arange(5) + .5) / 5 - .5:
        for sx in (np.arange(5) + .5) / 5 - .5:
            separation = wcs.pixel_to_world(xx + sx, yy + sy).separation(coordinate).rad
            weights += (separation <= config.radius_px * angular_pixel) / 25
    radius = wcs.pixel_to_world(xx, yy).separation(coordinate).rad
    valid = (np.isfinite(image) & np.isfinite(variance) & (variance > 0)
             & ((flags.astype(np.uint64) & config.rejected_flag_bits) == 0))
    if np.any((weights > 0) & ~valid):
        affected = (weights > 0) & ~valid
        combined = int(np.bitwise_or.reduce(flags[affected].astype(np.uint64))) & config.rejected_flag_bits
        labels = [flag_labels.get(bit, f"bit {bit}") for bit in range(32) if combined & (1 << bit)]
        raise ValueError(f"Aperture contains invalid or rejected pixels (n={int(affected.sum())}; flags={labels})")
    annulus = ((radius >= config.annulus_inner_px * angular_pixel) & (radius <= outer) & valid
               & ((flags.astype(np.uint64) & config.background_rejected_flag_bits) == 0))
    n_background = int(annulus.sum())
    if n_background < 20:
        raise ValueError(f"Fewer than 20 valid background pixels (n={n_background}; additional background mask={config.background_rejected_flag_bits})")
    background = float(np.mean(image[annulus]))
    bg_variance = max(float(variance[annulus].sum() / n_background ** 2),
                      float(np.var(image[annulus], ddof=1) / n_background))
    conversion = _solid_angles(wcs, xx, yy) * 1e6  # MJy/sr to Jy per pixel
    flux_weights = weights * conversion
    area = flux_weights.sum()
    # np.where avoids NaN * zero contaminating otherwise valid apertures.
    flux = float(np.sum(flux_weights * np.where(valid, image - background, 0)))
    flux_variance = float(np.sum(flux_weights ** 2 * np.where(valid, variance, 0)) + area ** 2 * bg_variance)
    notes = ["Preliminary finite-aperture flux; no PSF/aperture or colour correction",
             "Independent pixel errors; calibration systematics and covariance excluded",
             "Sky aperture supersampled 5x5; WCS-derived spherical pixel solid angles",
             "Annular mean background; neighbours and diffuse structure require inspection",
             "Detector alone is not a compatible spectral band; no automatic light curve"]
    if target.target_id == "RW Aurigae":
        notes.append("RW Aur components may be blended; do not attribute flux to component A")
    if not config.background_rejected_flag_bits & (1 << 21):
        notes.append("SOURCE-flagged background pixels are not excluded in this legacy-compatible configuration; photometry remains unvalidated")
    if mjd is None or scale is None:
        notes.append("Observation epoch or time scale missing; excluded from time comparisons")
    return Measurement(target=target, observation=cutout.observation, dataset_version=version,
        input_path=cutout.asset.path, mjd=mjd, time_scale=scale, detector=str(header["DETECTOR"]),
        wavelength_um=wavelength_um, bandwidth_um=bandwidth_um,
        flux_jy=flux, uncertainty_jy=np.sqrt(flux_variance),
        background_mjy_sr=background, aperture=config, warnings=notes)
