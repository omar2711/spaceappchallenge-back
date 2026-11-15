"""SPLICES cone search through official IRSA TAP; no automatic name resolution."""

from io import BytesIO

import httpx
from astropy.table import Table

from .models import CatalogQuery, CatalogResult, CatalogSource, Provenance

TAP_URL = "https://irsa.ipac.caltech.edu/TAP/sync"


def build_adql(query: CatalogQuery) -> str:
    """Only validated numbers are interpolated; table and columns are fixed."""
    return (f"SELECT TOP {query.limit} source_id, ra, dec FROM splices "
            "WHERE 1=CONTAINS(POINT('ICRS',ra,dec),"
            f"CIRCLE('ICRS',{query.ra_deg},{query.dec_deg},{query.radius_deg})) "
            "ORDER BY source_id")


def query_splices(query: CatalogQuery, client: httpx.Client) -> CatalogResult:
    """Caller owns client lifecycle/timeout; network and service errors propagate.

    Results are candidates, never evidence of a molecular detection. A full page
    may be truncated; no claim of catalog completeness is made.
    """
    response = client.get(TAP_URL, params={"REQUEST": "doQuery", "LANG": "ADQL",
                                          "FORMAT": "votable", "QUERY": build_adql(query)})
    response.raise_for_status()
    table = Table.read(BytesIO(response.content), format="votable")
    sources = [CatalogSource(source_id=str(row["source_id"]),
                             ra_deg=float(row["ra"]), dec_deg=float(row["dec"]))
               for row in table]
    return CatalogResult(query=query, sources=sources,
                         possibly_truncated=len(sources) >= query.limit,
                         provenance=Provenance(kind="observation", source=TAP_URL + "#splices"))
