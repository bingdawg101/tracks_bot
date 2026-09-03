"""Radancy / TalentBrew career sites (Citi, Cargill, and many large employers).

The site's own search returns an HTML fragment wrapped in JSON:
    GET https://{host}/search-jobs/results?CurrentPage=N&RecordsPerPage=100&format=json
    -> {"results": "<section data-total-pages=..><ul><li><a href data-job-id><h3>..</h3>
        <span class='job-location'>..</span></a></li>..</ul></section>", ...}

Configure as:
    source: {host: jobs.citi.com}
    source: {host: careers.cargill.com, lang: en}   # some sites prefix paths with /en
"""

from __future__ import annotations

import httpx
from selectolax.parser import HTMLParser

from ..models import RawPosting, clean_text
from .base import Adapter, AdapterError

_PER_PAGE = 100
_MAX_PAGES = 8

# Radancy's endpoint 400s / returns empty unless the whole param set is present.
_BASE_PARAMS = {
    "ActiveFacetID": 0, "Distance": 50, "RadiusUnitType": 0, "Keywords": "", "Location": "",
    "ShowRadius": "False", "IsPagination": "True", "CustomFacetName": "", "FacetTerm": "",
    "FacetType": 0, "SearchResultsModuleName": "Search Results",
    "SearchFiltersModuleName": "Search Filters",
    "SortCriteria": 5, "SortDirection": 1,   # 5/1 = most recently posted first
    "SearchType": 5, "PostalCode": "", "format": "json",
}


class RadancyAdapter(Adapter):
    name = "radancy"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        host = self._require("host")
        lang = str(self.source.get("lang", "")).strip("/")
        prefix = f"https://{host}/{lang}".rstrip("/")
        results_url = f"{prefix}/search-jobs/results"
        keyword = str(self.source.get("keyword", ""))

        rows: list[RawPosting] = []
        pages = _MAX_PAGES
        for page in range(1, pages + 1):
            data = await self._get_json(
                client, results_url,
                params={
                    **_BASE_PARAMS,
                    "CurrentPage": page, "RecordsPerPage": _PER_PAGE, "Keywords": keyword,
                },
            )
            if not isinstance(data, dict) or "results" not in data:
                raise AdapterError(f"{self.firm.slug}: unexpected Radancy payload")
            frag = HTMLParser(data["results"])
            if page == 1:
                sec = frag.css_first("section[data-total-pages]")
                if sec:
                    pages = min(int(sec.attributes.get("data-total-pages") or 1), _MAX_PAGES)
            items = frag.css("li a[data-job-id], li a[href*='/job/']")
            if not items:
                break
            for a in items:
                title_el = a.css_first("h3")
                loc_el = a.css_first(".job-location")
                href = a.attributes.get("href", "") or ""
                rows.append(
                    RawPosting(
                        source_id=clean_text(a.attributes.get("data-job-id") or href),
                        title=clean_text(title_el.text() if title_el else a.text()),
                        location=clean_text(loc_el.text() if loc_el else ""),
                        url=href if href.startswith("http") else f"https://{host}{href}",
                    )
                )
        # de-dupe by source_id (pagination overlap)
        seen: dict[str, RawPosting] = {}
        for r in rows:
            seen.setdefault(r.source_id, r)
        return list(seen.values())
