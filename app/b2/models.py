"""JSON-safe science contracts. All measurements require explicit provenance."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Number = Annotated[float, Field(allow_inf_nan=False)]
Positive = Annotated[Number, Field(gt=0)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Provenance(Contract):
    """Origin of the supplied data; synthetic never means an observation."""

    kind: Literal["synthetic", "observation"]
    source: str = Field(min_length=1, description="Dataset identifier or official URI")


class LightCurve(Contract):
    """One calibrated band only. Epochs are MJD in the declared time scale."""

    target: Literal["RW Aurigae", "R Draconis"]
    band: str = Field(min_length=1)
    time_scale: Literal["utc", "tdb", "tt"]
    mjd: list[Number] = Field(min_length=2)
    values: list[Number]
    uncertainty: list[Positive]
    unit: Literal["mag", "Jy", "mJy"]
    provenance: Provenance

    @model_validator(mode="after")
    def matching(self) -> "LightCurve":
        if not len(self.mjd) == len(self.values) == len(self.uncertainty):
            raise ValueError("Epoch, value and uncertainty lengths must match")
        return self


class CurveSummary(Contract):
    curve: LightCurve
    weighted_mean: Number
    mean_uncertainty: Positive
    peak_to_peak: Number
    chi_square_constant: Number
    degrees_of_freedom: int


class Spectrum(Contract):
    """Calibrated 1-D spectrum; wavelength in vacuum micrometres, no extraction implied."""

    wavelength_um: list[Positive] = Field(min_length=2)
    flux: list[Number]
    uncertainty: list[Positive]
    flux_unit: Literal["Jy", "mJy", "MJy/sr"]
    provenance: Provenance

    @model_validator(mode="after")
    def matching(self) -> "Spectrum":
        if not len(self.wavelength_um) == len(self.flux) == len(self.uncertainty):
            raise ValueError("Spectral arrays must have equal lengths")
        if any(b <= a for a, b in zip(self.wavelength_um, self.wavelength_um[1:])):
            raise ValueError("Wavelengths must be strictly increasing")
        return self


class ContinuumRequest(Contract):
    """Continuum must be supplied in the spectrum's flux unit at each sample."""

    spectrum: Spectrum
    continuum: list[Positive]

    @model_validator(mode="after")
    def matching(self) -> "ContinuumRequest":
        if len(self.continuum) != len(self.spectrum.flux):
            raise ValueError("Continuum must match spectrum length")
        if any(f <= 0 for f in self.spectrum.flux):
            raise ValueError("Optical depth requires strictly positive flux")
        return self


class ProcessedSpectrum(Contract):
    spectrum: Spectrum
    normalized_flux: list[Number]
    optical_depth: list[Number]
    optical_depth_uncertainty: list[Positive]
    interpretation: Literal["No molecular detection inferred"] = "No molecular detection inferred"


class FitsAsset(Contract):
    """Proposed B1 adapter contract, not an existing B1 manifest schema."""

    path: str = Field(min_length=1, description="Relative path inside trusted data root")
    hdu: int | str = Field(description="Explicit science HDU index or name")
    provenance: Provenance


class DifferenceRequest(Contract):
    science: FitsAsset
    reference: FitsAsset
    reference_scale: Positive = 1.0


class DifferenceResult(Contract):
    """science - scale * reference; invalid pixels are JSON null."""

    pixels: list[list[Number | None]]
    valid_pixels: int
    unit: str
    science: FitsAsset
    reference: FitsAsset
    reference_scale: Positive


class CatalogQuery(Contract):
    ra_deg: Annotated[Number, Field(ge=0, lt=360)]
    dec_deg: Annotated[Number, Field(ge=-90, le=90)]
    radius_deg: Annotated[Positive, Field(le=1)]
    limit: int = Field(default=100, ge=1, le=10000)


class CatalogSource(Contract):
    source_id: str
    ra_deg: Number
    dec_deg: Number


class CatalogResult(Contract):
    query: CatalogQuery
    sources: list[CatalogSource]
    possibly_truncated: bool
    provenance: Provenance


class CometPlan(Contract):
    target: Literal["3I/ATLAS"] = "3I/ATLAS"
    assets: list[FitsAsset]
    status: Literal["awaiting_data", "awaiting_geometry_and_calibration"]
    required: list[str]
