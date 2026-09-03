"""Glencore — glencore.com careers.

Custom CMS REST feed used by the careers site, no auth:
    GET https://www.glencore.com/.rest/api/v2/careers/
        ?locale=en&sortBy=date-desc&offset=0&limit=50&searchCriteria={}&keyword=

adapter: glencore   (no source config needed)
"""

from __future__ import annotations

import httpx

from ..models import RawPosting, clean_text, stable_id
from .base import Adapter, AdapterError

_URL = "https://www.glencore.com/.rest/api/v2/careers/"
_PAGE = 50
_MAX = 500


class GlencoreAdapter(Adapter):
    name = "glencore"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        rows: list[dict] = []
        offset = 0
        total = None
        while True:
            data = await self._get_json(
                client, _URL,
                params={
                    "locale": "en", "sortBy": "date-desc",
                    "offset": offset, "limit": _PAGE,
                    "searchCriteria": "{}", "keyword": "",
                },
            )
            if not isinstance(data, dict) or "data" not in data:
                raise AdapterError(f"{self.firm.slug}: unexpected Glencore payload")
            batch = data["data"]
            rows.extend(batch)
            if total is None:
                total = min(int(data.get("totalResults", len(batch))), _MAX)
            offset += _PAGE
            if offset >= total or not batch:
                break

        out: list[RawPosting] = []
        for j in rows:
            loc = ", ".join(
                clean_text(p) for p in (j.get("city"), j.get("region"), j.get("country"))
                if clean_text(p) and clean_text(p) != "\u200b"
            )
            if not loc:
                # location often only in the highlights list, e.g. ["title", "London - UK", ...]
                hl = [clean_text(h) for h in (j.get("highlights") or [])]
                loc = hl[1] if len(hl) > 1 else ""
            jid = clean_text(str(j.get("id") or j.get("jobId") or "")) or stable_id(j.get("title", ""))
            out.append(
                RawPosting(
                    source_id=jid,
                    title=clean_text(j.get("title", "")),
                    location=loc,
                    url=clean_text(j.get("url", "") or j.get("applyUrl", ""))
                    or f"https://www.glencore.com/careers/jobs?id={jid}",
                    description=clean_text(j.get("description", ""))[:4000],
                    updated_at=clean_text(str(j.get("postingDate", ""))),
                )
            )
        return out
