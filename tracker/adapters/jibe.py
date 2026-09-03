"""Jibe / iCIMS career sites (SIG / Susquehanna).

Public JSON search API, no auth. A plain request works as long as it asks for JSON
(`Accept: application/json`); the earlier "data: null" symptom came from a missing
Accept header, not a cookie/CSRF wall.

    GET https://{host}/api/jobs?page=N&limit=100&sortBy=relevance&descending=false&internal=false
    -> {"jobs": [{"data": {title, req_id, slug, city, state, country, full_location,
        categories, employment_type, posted_date, apply_url, brand, ...}}],
        "totalCount": N, "count": N}

Configure as:
    source: {host: careers.sig.com}
    source: {host: careers.sig.com, location: London}   # optional server-side location filter
"""

from __future__ import annotations

import html as _html

import httpx
from selectolax.parser import HTMLParser

from ..models import RawPosting, clean_text, stable_id
from .base import Adapter, AdapterError

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
_LIMIT = 100
_MAX_PAGES = 12


def _strip_html(raw: str) -> str:
    if not raw:
        return ""
    return clean_text(HTMLParser(_html.unescape(raw)).text(separator=" "))


class JibeAdapter(Adapter):
    name = "jibe"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        host = self._require("host")
        url = f"https://{host}/api/jobs"
        params = {
            "sortBy": "relevance",
            "descending": "false",
            "internal": "false",
            "limit": _LIMIT,
        }
        location = str(self.source.get("location", "")).strip()
        if location:
            params["location"] = location

        rows: list[RawPosting] = []
        seen: set[str] = set()
        for page in range(1, _MAX_PAGES + 1):
            data = await self._get_json(
                client,
                url,
                params={**params, "page": page},
                headers={"Accept": "application/json", "User-Agent": _UA},
            )
            if not isinstance(data, dict) or "jobs" not in data:
                raise AdapterError(f"{self.firm.slug}: unexpected Jibe payload")
            jobs = data.get("jobs") or []
            if page == 1 and not jobs and data.get("count"):
                raise AdapterError(f"{self.firm.slug}: Jibe returned no jobs for count={data.get('count')}")
            new = 0
            for entry in jobs:
                d = entry.get("data") or {}
                jid = clean_text(str(d.get("req_id") or d.get("slug") or "")) or stable_id(
                    d.get("title", ""), d.get("full_location", "")
                )
                if jid in seen:
                    continue
                seen.add(jid)
                new += 1
                cats = ", ".join(
                    clean_text(c.get("name", "")) for c in (d.get("categories") or []) if c.get("name")
                )
                rows.append(
                    RawPosting(
                        source_id=jid,
                        title=clean_text(d.get("title", "")),
                        location=clean_text(d.get("full_location") or d.get("location_name") or ""),
                        url=clean_text(d.get("apply_url", "")) or url,
                        description=_strip_html(d.get("description", ""))[:2000],
                        department=clean_text(d.get("department") or cats),
                        employment_type=clean_text(d.get("employment_type", "")).replace("_", " ").title(),
                        updated_at=clean_text(str(d.get("posted_date", "")))[:10],
                    )
                )
            if new == 0 or len(jobs) < _LIMIT:
                break
        return rows
