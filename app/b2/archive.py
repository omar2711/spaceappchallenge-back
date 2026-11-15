"""Bounded IRSA SIA2 discovery and IBE FITS cutout cache. No import-time I/O."""

import hashlib
import json
import time
import warnings
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.table import Table

from .models import FitsAsset, Provenance
from .observation_models import (CachedCutout, DownloadLimits, Observation,
                                 ObservationQuery, ObservationSearch, Target)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cell(row: Any, name: str) -> Any:
    value = row[name] if name in row.colnames else None
    if value is None or np.ma.is_masked(value):
        return None
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    return value


def search_observations(query: ObservationQuery, *, irsa: Any = None,
                        attempts: int = 2) -> ObservationSearch:
    """SIA2 MAXREC is server-side, unlike a post-query slice.

    Each call uses a private client. Exceptions propagate after bounded retries;
    empty is reserved for a successful response with no observations.
    """
    if not 1 <= attempts <= 3:
        raise ValueError("attempts must be between 1 and 3")
    if irsa is None:
        from astroquery.ipac.irsa import IrsaClass
        from requests.adapters import HTTPAdapter

        class TimeoutAdapter(HTTPAdapter):
            def send(self, request: Any, stream: bool = False, timeout: Any = None,
                     verify: Any = True, cert: Any = None, proxies: Any = None) -> Any:
                return super().send(request, stream=stream, timeout=(10, 30),
                                    verify=verify, cert=cert, proxies=proxies)

        irsa = IrsaClass()
        # PyVO uses the requests session directly; Irsa.TIMEOUT does not bound it.
        irsa._session.mount("https://", TimeoutAdapter())
    coord = SkyCoord(query.ra_deg, query.dec_deg, unit="deg")
    for attempt in range(attempts):
        try:
            with warnings.catch_warnings(record=True) as caught:
                result = irsa.query_sia(pos=(coord, query.radius_deg * u.deg),
                                        collection=query.collections, maxrec=query.limit)
                table = result if isinstance(result, Table) else result.to_table()
            break
        except Exception:
            if attempt + 1 == attempts:
                raise
            time.sleep(attempt + 1)
    observations = []
    for row in table[:query.limit]:
        for name in ("obs_id", "obs_collection", "access_url"):
            if _cell(row, name) is None:
                raise ValueError(f"SIA response lacks required {name}")
        band = _cell(row, "energy_bandpassname")
        observations.append(Observation(
            observation_id=str(_cell(row, "obs_id")),
            collection=str(_cell(row, "obs_collection")),
            access_url=str(_cell(row, "access_url")),
            band=str(band) if band is not None else None,
            detector=str(band)[-1] if band in {f"SPHEREx-D{i}" for i in range(1, 7)} else None,
            mjd_start=_cell(row, "t_min"), mjd_end=_cell(row, "t_max"),
            # ObsCore timestamps use MJD, but time scale is not invented here.
            wavelength_min_m=_cell(row, "em_min"), wavelength_max_m=_cell(row, "em_max")))
    messages = [str(w.message) for w in caught]
    return ObservationSearch(query=query, observations=observations,
        status="ok" if observations else "empty", queried_at_utc=utc_now(),
        possibly_truncated=len(table) >= query.limit or any("overflow" in s.lower() for s in messages),
        warnings=messages + ["MAXREC subset is not a complete or chronologically selected sample"])


def cutout_url(observation: Observation, target: Target, size_deg: float) -> str:
    """Use official IBE center/size parameters, never silently fetch a full MEF."""
    if not 0 < size_deg <= .05:
        raise ValueError("Cutout size must be in (0, .05] degrees")
    parsed = urlsplit(observation.access_url)
    if (parsed.scheme != "https" or parsed.netloc != "irsa.ipac.caltech.edu"
            or not parsed.path.startswith("/ibe/data/spherex/")
            or not parsed.path.endswith(".fits") or ".." in parsed.path):
        raise ValueError("Expected an official IRSA SPHEREx IBE FITS URL")
    query = urlencode({"center": f"{target.ra_deg},{target.dec_deg}d", "size": size_deg})
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def _verify_fits(content: bytes) -> None:
    with fits.open(BytesIO(content), memmap=False) as hdus:
        hdus.verify("exception")
        if "IMAGE" not in hdus or hdus["IMAGE"].data is None:
            raise ValueError("Cutout lacks IMAGE data")
        if hdus["IMAGE"].data.ndim != 2 or max(hdus["IMAGE"].data.shape) > 128:
            raise ValueError("Server returned an oversized or non-image cutout")
        for hdu in hdus:
            if hdu.data is not None:
                _ = hdu.data  # force decompression before admitting into cache


class CutoutCache:
    """Per-run file/byte/time budgets, including retries and cache hits.

    Root is server configuration, never supplied by an untrusted HTTP payload.
    Uses only official URLs; redirects are rejected. Cache entries are immutable.
    """

    def __init__(self, root: Path, client: httpx.Client, limits: DownloadLimits):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.client = client
        self.limits = limits
        self.bytes_read = 0
        self.files = 0
        self.started = time.monotonic()

    def _budget(self) -> None:
        if time.monotonic() - self.started >= self.limits.max_seconds:
            raise ValueError("Download wall-time budget exhausted")
        if self.bytes_read >= self.limits.max_total_bytes:
            raise ValueError("Download byte budget exhausted")

    def fetch(self, observation: Observation, target: Target) -> CachedCutout:
        if self.files >= self.limits.max_files:
            raise ValueError("Download file-count budget exhausted")
        self._budget()
        self.files += 1
        url = cutout_url(observation, target, self.limits.cutout_size_deg)
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.root / f"{key}.fits"
        metadata_path = self.root / f"{key}.json"
        for entry in (path, metadata_path):
            if entry.is_symlink():
                raise ValueError("Cache symlinks are not allowed")
        hit = path.exists()
        if hit:
            if path.stat().st_size > self.limits.max_file_bytes:
                raise ValueError("Cached FITS exceeds file budget")
            content = path.read_bytes()
            self.bytes_read += len(content)
            if self.bytes_read > self.limits.max_total_bytes:
                raise ValueError("Cached FITS exceeds total budget")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata["sha256"] != hashlib.sha256(content).hexdigest() or metadata["url"] != url:
                raise ValueError("Cache checksum or URL mismatch")
        else:
            for attempt in range(2):
                self._budget()
                try:
                    remaining = self.limits.max_seconds - (time.monotonic() - self.started)
                    with self.client.stream("GET", url, follow_redirects=False,
                                            timeout=min(30, remaining)) as response:
                        response.raise_for_status()
                        if response.is_redirect:
                            raise ValueError("Redirects are not accepted for FITS downloads")
                        content = b""
                        for chunk in response.iter_bytes(65536):
                            self._budget()
                            self.bytes_read += len(chunk)
                            if (len(content) + len(chunk) > self.limits.max_file_bytes
                                    or self.bytes_read > self.limits.max_total_bytes):
                                raise ValueError("FITS download exceeds byte budget")
                            content += chunk
                    break
                except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                    if (attempt == 1 or (isinstance(exc, httpx.HTTPStatusError)
                            and exc.response.status_code not in (429, 500, 502, 503, 504))):
                        raise
                    time.sleep(1)
            _verify_fits(content)
            metadata = {"url": url, "sha256": hashlib.sha256(content).hexdigest(),
                        "retrieved_at_utc": utc_now()}
            # Never overwrite an existing user file or cache entry.
            with path.open("xb") as handle:
                handle.write(content)
            with metadata_path.open("x", encoding="utf-8") as handle:
                json.dump(metadata, handle, indent=2)
        _verify_fits(content)
        return CachedCutout(observation=observation,
            asset=FitsAsset(path=path.name, hdu="IMAGE",
                            provenance=Provenance(kind="observation", source=url)),
            cutout_url=url, sha256=metadata["sha256"], size_bytes=len(content),
            retrieved_at_utc=metadata["retrieved_at_utc"], cache_hit=hit)
