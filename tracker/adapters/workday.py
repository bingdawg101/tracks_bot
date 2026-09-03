"""Workday-hosted career sites.

Workday exposes a public JSON search endpoint used by its own front-end:
    POST https://{host}/wday/cxs/{tenant}/{site}/jobs
    body: {"appliedFacets": {...}, "limit": 20, "offset": 0, "searchText": ""}

`limit` is capped at 20 by Workday. To avoid paging through thousands of global roles
every run, we first read the `Location_Country` facet and re-query with the UK value
applied (override via `source.countries`).

Configure as:
    source: {tenant: morganstanley, wd: wd5, site: External}
    source: {tenant: x, site: Careers, host: careers.x.com}         # explicit host
    source: {tenant: x, wd: wd3, site: Ext, countries: [United Kingdom, Ireland]}
"""

from __future__ import annotations

import httpx

from ..models import RawPosting, clean_text, stable_id
from .base import Adapter, AdapterError

_LIMIT = 20
_MAX = 600  # safety cap on total rows pulled per firm
_COUNTRY_FACET = "Location_Country"


class WorkdayAdapter(Adapter):
    name = "workday"

    def _base(self) -> str:
        tenant = self._require("tenant")
        site = self._require("site")
        host = str(self.source.get("host", "")).strip()
        if not host:
            wd = str(self.source.get("wd", "")).strip()
            if not wd:
                raise AdapterError(f"{self.firm.slug}: set source.wd (e.g. wd5) or source.host")
            host = f"{tenant}.{wd}.myworkdayjobs.com"
        return f"https://{host}/wday/cxs/{tenant}/{site}"

    async def _search(self, client, url, facets, offset):
        return await self._post_json(
            client, url,
            json={"appliedFacets": facets, "limit": _LIMIT, "offset": offset, "searchText": ""},
        )

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        base = self._base()
        jobs_url = f"{base}/jobs"
        wanted = {c.lower() for c in (self.source.get("countries") or ["United Kingdom"])}

        first = await self._search(client, jobs_url, {}, 0)
        if not isinstance(first, dict) or "jobPostings" not in first:
            raise AdapterError(f"{self.firm.slug}: unexpected Workday payload")

        # Resolve the country facet ids we care about.
        facet_ids: list[str] = []
        for facet in first.get("facets", []):
            if facet.get("facetParameter") == _COUNTRY_FACET:
                for val in facet.get("values", []):
                    if clean_text(val.get("descriptor", "")).lower() in wanted:
                        facet_ids.append(val["id"])

        if facet_ids:
            facets = {_COUNTRY_FACET: facet_ids}
            page0 = await self._search(client, jobs_url, facets, 0)
        else:
            facets, page0 = {}, first  # no UK facet — fall back to unfiltered (capped)

        total = min(int(page0.get("total", 0)), _MAX)
        rows = list(page0.get("jobPostings", []))
        for offset in range(_LIMIT, total, _LIMIT):
            page = await self._search(client, jobs_url, facets, offset)
            rows.extend(page.get("jobPostings", []))

        host_root = base.rsplit("/wday/", 1)[0]
        return [self._to_posting(r, host_root) for r in rows]

    def _to_posting(self, row: dict, host_root: str) -> RawPosting:
        path = row.get("externalPath", "")
        bullets = row.get("bulletFields") or []
        sid = clean_text(bullets[0]) if bullets else ""
        if not sid:
            sid = stable_id(path or row.get("title", ""))
        return RawPosting(
            source_id=sid,
            title=clean_text(row.get("title", "")),
            location=clean_text(row.get("locationsText", "")),
            url=f"{host_root}{path}" if path else host_root,
            employment_type="",  # list rows omit it; classifier uses title/description
            updated_at=clean_text(row.get("postedOn", "")),
        )
