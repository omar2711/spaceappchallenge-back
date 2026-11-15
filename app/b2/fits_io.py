"""Explicit local FITS access; never downloads or guesses HDUs."""

from pathlib import Path

import numpy as np
from astropy.io import fits
from numpy.typing import NDArray

from .models import FitsAsset


def read_image(asset: FitsAsset, data_root: Path) -> tuple[NDArray[np.float64], fits.Header]:
    """Copy a 2-D image from a trusted root; reject traversal and symlink escapes."""
    root = data_root.resolve(strict=True)
    relative = Path(asset.path)
    if relative.is_absolute() or relative.drive:
        raise ValueError("FITS path must be relative to data_root")
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ValueError("FITS path escapes data_root")
    if isinstance(asset.hdu, int) and asset.hdu < 0:
        raise ValueError("HDU index cannot be negative")
    with fits.open(path, memmap=False) as hdus:
        hdu = hdus[asset.hdu]
        if hdu.data is None or hdu.data.ndim != 2:
            raise ValueError("Selected HDU must contain a 2-D image")
        return np.array(hdu.data, dtype=np.float64, copy=True), hdu.header.copy()
