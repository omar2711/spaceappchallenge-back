"""Validated image differences exported without inventing temporal compatibility."""

import hashlib
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from .fits_io import read_image
from .models import Contract
from .observation_models import FrameSpec, ValidatedDifference
from .validated_images import validated_difference


class DifferenceArtifacts(Contract):
    result: ValidatedDifference
    input_sha256: dict[str, str]
    input_kind: str
    temporal_comparison_verified: bool = False
    warnings: list[str]


def export_difference(science: FrameSpec, reference: FrameSpec, root: Path,
                       output: Path) -> DifferenceArtifacts:
    """Calculate only after B2 checks, then write FITS, PNG and metadata JSON.

    No resampling or PSF matching. Equal IDs are attestations by B1; a genuine
    temporal comparison additionally requires distinct epochs and reviewed
    registration/PSF evidence. This exporter does not independently verify them.
    """
    result = validated_difference(science, reference, root)
    _, source_header = read_image(science.image, root)
    header = WCS(source_header).to_header(relax=True)
    header["BUNIT"] = result.unit
    header["BKGDIFF"] = result.background_offset
    synthetic = any(a.provenance.kind == "synthetic" for frame in (science, reference)
                    for a in (frame.image, frame.flags, frame.background_mask, frame.variance, frame.uncertainty)
                    if a is not None)
    header["SYNTHET"] = synthetic
    header["TEMPVER"] = False
    array = np.array([[np.nan if v is None else v for v in row] for row in result.pixels])
    hdus = [fits.PrimaryHDU(array, header), fits.ImageHDU(np.isfinite(array).astype(np.uint8), name="VALID")]
    if result.uncertainty is not None:
        errors = np.array([[np.nan if v is None else v for v in row] for row in result.uncertainty])
        eh = header.copy()
        hdus.append(fits.ImageHDU(errors, eh, name="UNCERTAINTY"))
    checksums = {}
    for frame in (science, reference):
        for asset in (frame.image, frame.flags, frame.variance, frame.uncertainty, frame.background_mask):
            if asset is not None:
                checksums[asset.path] = hashlib.sha256((root / asset.path).read_bytes()).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    fits.HDUList(hdus).writeto(output / "difference.fits", overwrite=False, checksum=True)
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    fig = Figure(figsize=(7, 5))
    FigureCanvasAgg(fig)
    ax = fig.add_subplot()
    valid = array[np.isfinite(array)]
    if not valid.size:
        raise ValueError("No valid difference pixels to display")
    vmax = max(float(np.percentile(np.abs(valid), 99)), np.finfo(float).eps)
    im = ax.imshow(array, origin="lower", cmap="RdBu_r", vmin=-vmax, vmax=vmax)
    ax.set(title="Synthetic validation only" if synthetic else "Difference; temporal interpretation requires review",
           xlabel="Registered pixel x", ylabel="Registered pixel y")
    fig.colorbar(im, ax=ax, label=result.unit)
    fig.tight_layout()
    fig.savefig(output / "difference.png", dpi=140)
    result.result_paths = ["difference.fits", "difference.png", "difference.json"]
    artifact = DifferenceArtifacts(result=result, input_sha256=checksums,
        input_kind="synthetic_present" if synthetic else "observational_inputs",
        warnings=["This result alone does not verify a temporal change or detection",
                  "B1 must provide reviewed PSF matching, response equivalence and registration"])
    with (output / "difference.json").open("x", encoding="utf-8") as handle:
        handle.write(artifact.model_dump_json(indent=2))
    return artifact
