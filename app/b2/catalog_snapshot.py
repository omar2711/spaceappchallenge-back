"""Small reproducible SPLICES snapshots with live schema, units and query status."""

from io import BytesIO
import time
from typing import Any, Literal

import httpx
import numpy as np
from astropy.io.votable import parse
from astropy.table import Table

from .archive import utc_now
from .catalog import TAP_URL
from .models import CatalogQuery, Contract, Number


class SplicesSnapshot(Contract):
    query: CatalogQuery
    adql: str | None
    protocol: Literal["TAP", "SCS"] = "TAP"
    endpoint: str = TAP_URL
    retrieved_at_utc: str
    dataset_doi: str = "10.26131/IRSA554"
    columns: dict[str, dict[str, str | None]]
    rows: list[dict[str, Number | str | None]]
    possibly_truncated: bool
    warnings: list[str]


def tap_table(adql: str, client: httpx.Client, *, maxrec: int = 100) -> tuple[Table, bool]:
    """Bounded TAP response and two attempts for transport/transient HTTP errors."""
    if not 1 <= maxrec <= 100:
        raise ValueError("maxrec must be between 1 and 100")
    for attempt in range(2):
        try:
            with client.stream("GET", TAP_URL, params={"REQUEST": "doQuery", "LANG": "ADQL",
                    "FORMAT": "votable", "MAXREC": maxrec, "QUERY": adql}, timeout=45,
                    follow_redirects=False) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes(65536):
                    content.extend(chunk)
                    if len(content) > 2_000_000:
                        raise ValueError("TAP response exceeds 2 MB budget")
            break
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if attempt or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in (429, 500, 502, 503, 504)):
                raise
            time.sleep(1)
    document = parse(BytesIO(content))
    overflow = False
    for resource in document.resources:
        for info in resource.infos:
            if info.name == "QUERY_STATUS":
                if info.value == "ERROR":
                    raise ValueError(f"IRSA TAP error: {info.content}")
                overflow |= info.value == "OVERFLOW"
    table = document.get_first_table().to_table(use_names_over_ids=True)
    if len(table) > maxrec:
        raise ValueError("TAP service ignored the row budget")
    return table, overflow


def splices_snapshot(query: CatalogQuery, client: httpx.Client) -> SplicesSnapshot:
    """Live schema first, fixed science-column allowlist, no molecular claims."""
    if query.limit > 10:
        raise ValueError("SPLICES demonstration snapshots are limited to 10 rows")
    schema, _ = tap_table("SELECT TOP 100 column_name,datatype,unit,description "
                          "FROM TAP_SCHEMA.columns WHERE table_name='splices'", client)
    available = {str(row["column_name"]).lower(): row for row in schema}
    required = ["source_id", "ra", "dec"]
    if any(name not in available for name in required):
        raise ValueError("SPLICES schema is missing source identity/coordinates")
    wanted = required + ["designation", "j", "jerr", "h", "herr", "k", "kerr",
                         "w1", "w1err", "w2", "w2err", "name"]
    names = [name for name in wanted if name in available]
    # Cheap indexed bounds before the exact spherical predicate. The direct
    # geometry-only query can scan millions of catalog rows on IRSA TAP.
    bounds = f"dec BETWEEN {max(-90, query.dec_deg-query.radius_deg)} AND {min(90, query.dec_deg+query.radius_deg)}"
    if abs(query.dec_deg) + query.radius_deg < 90:
        halfwidth = float(np.rad2deg(np.arcsin(np.sin(np.deg2rad(query.radius_deg)) / np.cos(np.deg2rad(query.dec_deg)))))
        lower, upper = (query.ra_deg-halfwidth) % 360, (query.ra_deg+halfwidth) % 360
        bounds += (f" AND ra BETWEEN {lower} AND {upper}" if lower <= upper
                   else f" AND (ra >= {lower} OR ra <= {upper})")
    adql = (f"SELECT TOP {query.limit} {','.join(names)} FROM splices "
        f"WHERE {bounds} AND 1=CONTAINS(POINT('ICRS',ra,dec),"
        f"CIRCLE('ICRS',{query.ra_deg},{query.dec_deg},{query.radius_deg}))")
    table, overflow = tap_table(adql, client, maxrec=query.limit)
    columns = {}
    for name in names:
        row = available[name]
        columns[name] = {key: None if np.ma.is_masked(row[key]) else str(row[key])
                         for key in ("datatype", "unit", "description")}
    rows: list[dict[str, Any]] = []
    for row in table:
        record: dict[str, Any] = {}
        for name in table.colnames:
            value = row[name]
            if np.ma.is_masked(value) or (isinstance(value, (float, np.floating)) and not np.isfinite(value)):
                record[name] = None
            elif name.lower() == "source_id":
                record[name] = str(value)  # preserve 64-bit identity in JavaScript
            elif isinstance(value, (int, np.integer)) and abs(int(value)) > 2**53:
                record[name] = str(value)
            elif isinstance(value, (int, float, np.number)):
                record[name] = float(value)
            else:
                record[name] = str(value)
        rows.append(record)
    return SplicesSnapshot(query=query, adql=adql, retrieved_at_utc=utc_now(),
        columns=columns, rows=rows, possibly_truncated=overflow or len(rows) >= query.limit,
        warnings=["SPLICES contains candidate ice sources, NOT confirmed molecular detections",
                  "Broadband catalog photometry is not a SPHEREx spectral measurement",
                  "Cite Ashby et al. (2023) and DOI 10.26131/IRSA554"])


def scs_splices_snapshot(query: CatalogQuery, client: httpx.Client) -> SplicesSnapshot:
    """Official SCS alternative when TAP geometry queries are unavailable.

    SCS has no MAXREC: enforce a tiny cone, 2 MB transfer cap, and explicit local
    row truncation. No query failure is ever converted into an empty catalog.
    """
    if query.radius_deg > .01 or query.limit > 10:
        raise ValueError("SCS demo requires radius <= .01 deg and limit <= 10")
    endpoint = "https://irsa.ipac.caltech.edu/SCS"
    for attempt in range(2):
        try:
            with client.stream("GET", endpoint, params={"table": "splices", "RA": query.ra_deg,
                    "DEC": query.dec_deg, "SR": query.radius_deg, "format": "votable"},
                    timeout=30, follow_redirects=False) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes(65536):
                    content.extend(chunk)
                    if len(content) > 2_000_000:
                        raise ValueError("SCS response exceeds 2 MB")
            break
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt:
                raise
            time.sleep(1)
    document = parse(BytesIO(content))
    for resource in document.resources:
        for info in resource.infos:
            if (info.name or "").lower() == "error" or (info.name == "QUERY_STATUS" and info.value == "ERROR"):
                raise ValueError(f"IRSA SCS error: {info.content or info.value}")
        for param in resource.params:
            if (param.name or "").lower() == "error":
                raise ValueError(f"IRSA SCS error: {param.value}")
    element = document.get_first_table()
    table = element.to_table(use_names_over_ids=True)
    fields = {field.name: field for field in element.fields}
    if any(c not in table.colnames for c in ("source_id", "ra", "dec")):
        raise ValueError("SCS result lacks source identity/coordinates")
    rows = []
    for row in table[:query.limit]:
        record: dict[str, Any] = {}
        for name in table.colnames:
            value = row[name]
            if np.ma.is_masked(value) or (isinstance(value, (float, np.floating)) and not np.isfinite(value)):
                record[name] = None
            elif name == "source_id":
                record[name] = str(value)
            elif isinstance(value, (int, np.integer)) and abs(int(value)) > 2**53:
                record[name] = str(value)
            elif isinstance(value, (int, float, np.number)):
                record[name] = float(value)
            else:
                record[name] = str(value)
        rows.append(record)
    columns = {name: {"datatype": str(field.datatype), "unit": str(field.unit) if field.unit else None,
                      "description": field.description} for name, field in fields.items()}
    return SplicesSnapshot(query=query, adql=None, protocol="SCS", endpoint=endpoint,
        retrieved_at_utc=utc_now(), columns=columns, rows=rows,
        possibly_truncated=len(table) > query.limit,
        warnings=["SPLICES contains candidate ice sources, NOT confirmed molecular detections",
                  "SCS has no server-side row cap; tiny cone and byte cap used",
                  "Rows are not automatically identified with the queried target",
                  "Broadband catalog photometry is not SPHEREx spectral photometry",
                  "Cite Ashby et al. (2023) and DOI 10.26131/IRSA554"])
