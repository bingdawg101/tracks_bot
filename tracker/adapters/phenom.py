"""Phenom People career sites (RBC, BMO, Marshall Wace, Brevan Howard, and many more).

Phenom server-renders the first page of search results into `window.phApp.ddo` on the
search-results HTML page. We read that JSON and page with the `from` offset.

    GET https://{host}{path}?keywords={kw}&sortBy=Most recent&from={n}
    -> ...<script> phApp.ddo = { ... "eagerLoadRefineSearch": {
         "totalHits": N, "data": {"jobs": [{title, location, type, postedDate, jobId,
         applyUrl, category, ...}]}}} ;</script>...

Configure as:
    source: {host: jobs.rbc.com, path: /ca/en/search-results}
    source: {host: careers.mwam.com, path: /en/search-results, keyword: "trading quant research"}
"""

from __future__ import annotations

import json

import httpx

from ..models import RawPosting, clean_text, stable_id
from .base import Adapter, AdapterError

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
_PAGE = 10
_MAX_PAGES = 12
_MARKER = "phApp.ddo = "


def _extract_ddo(html: str) -> dict:
    i = html.find(_MARKER)
    if i < 0:
        raise AdapterError("phApp.ddo not found in page")
    i += len(_MARKER)
    # brace-match to the closing '};'
    depth, j, in_str, esc = 0, i, False, False
    while j < len(html):
        ch = html[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(html[i:j + 1])
        j += 1
    raise AdapterError("could not parse phApp.ddo")


class PhenomAdapter(Adapter):
    name = "phenom"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        host = self._require("host")
        path = self.source.get("path", "/en/search-results")
        keyword = str(self.source.get("keyword", ""))
        url = f"https://{host}{path}"

        rows: list[RawPosting] = []
        seen: set[str] = set()
        total = None
        for page in range(_MAX_PAGES):
            resp = await client.get(
                url,
                params={"keywords": keyword, "sortBy": "Most recent", "from": page * _PAGE},
                headers={"User-Agent": _UA},
            )
            resp.raise_for_status()
            block = _extract_ddo(resp.text).get("eagerLoadRefineSearch") or {}
            jobs = (block.get("data") or {}).get("jobs") or []
            if page == 0:
                total = int(block.get("totalHits", 0))
                if not jobs and total:
                    raise AdapterError(f"{self.firm.slug}: Phenom returned no jobs for total={total}")
            new = 0
            for j in jobs:
                jid = clean_text(str(j.get("jobId") or j.get("reqId") or ""))
                if not jid:
                    jid = stable_id(j.get("title", ""), j.get("location", ""))
                if jid in seen:
                    continue
                seen.add(jid)
                new += 1
                rows.append(
                    RawPosting(
                        source_id=jid,
                        title=clean_text(j.get("title", "")),
                        location=clean_text(j.get("location") or j.get("cityStateCountry", "")),
                        url=clean_text(j.get("applyUrl", "")) or url,
                        description=clean_text(j.get("descriptionTeaser", ""))[:2000],
                        department=clean_text(j.get("category", "")),
                        employment_type=clean_text(j.get("type", "")),
                        updated_at=clean_text(str(j.get("postedDate", "")))[:10],
                    )
                )
            if new == 0 or (total and len(seen) >= total):
                break
        return rows
