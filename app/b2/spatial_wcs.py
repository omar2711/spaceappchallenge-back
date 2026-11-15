"""Compare spatial grids without mistaking observation epochs for pixel geometry."""

from astropy.io import fits
from astropy.wcs import WCS


def same_celestial_grid(first: fits.Header, second: fits.Header) -> bool:
    """Strict 2-D celestial WCS/SIP comparison, independent of exposure metadata.

    Dates, time references and observatory positions can be retained by Astropy's
    to_header even for a celestial WCS. They are not the spatial pixel transform.
    Band, detector, epoch and PSF compatibility must be checked separately.
    """
    grids = []
    for header in (first, second):
        wcs = WCS(header)
        if not wcs.has_celestial or wcs.pixel_n_dim != 2:
            return False
        grid = wcs.celestial.to_header(relax=True)
        for key in list(grid):
            if key.startswith(("DATE-", "MJD", "JDREF", "TIME", "TREF", "OBSGEO")):
                del grid[key]
        grids.append(grid)
    return grids[0] == grids[1]
