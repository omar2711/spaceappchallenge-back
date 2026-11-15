"""Only compare externally verified spectral responses, never detector ranges."""

from .observation_models import CompatibleSamples, Measurement


def group_compatible_samples(measurements: list[Measurement]) -> CompatibleSamples:
    """Group/sort, without resampling or averaging. Missing response IDs excluded.

    response_id must identify the effective response AND applicable photometric
    calibration (B1/reviewer attestation), not a rounded central wavelength.
    Matching IDs alone do not establish PSF or aperture corrections.
    """
    groups: dict[tuple[str, ...], list[Measurement]] = {}
    excluded = []
    seen = set()
    for sample in measurements:
        identity = (sample.observation.access_url, sample.input_path)
        if not sample.response_id or sample.mjd is None or sample.time_scale is None or identity in seen:
            excluded.append(sample)
            continue
        seen.add(identity)
        key = (sample.target.model_dump_json(), sample.observation.collection,
               sample.dataset_version, sample.detector, sample.response_id,
               sample.aperture.model_dump_json(), sample.time_scale)
        groups.setdefault(key, []).append(sample)
    return CompatibleSamples(groups=[sorted(group, key=lambda m: m.mjd if m.mjd is not None else 0)
                                      for group in groups.values()], excluded=excluded,
        warnings=["Response IDs require external calibration review; no automatic LVF channel equivalence",
                  "Singletons and simultaneous samples are not a temporal light curve",
                  "All samples remain preliminary aperture photometry"])
