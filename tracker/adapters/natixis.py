"""Natixis / Groupe BPCE careers site (recrutement.natixis.com).

A WordPress-based site whose search widget POSTs to a clean JSON API — found via
render.capture() while the page's own search box loaded more results:

    POST https://recrutement.natixis.com/app/wp-json/bpce/v1/search/jobs
    body: {"lang": "en", "keyword": "", "tax_*": "", ..., "from": N, "size": 9}
    -> {"data": {"total": N, "items": [{title, localisation, contract: [...],
        sector: [...], job: [...], brand: [...], link: {url}, description}]}}

`contract` is a structured, authoritative employment-type list (e.g. ["Internship"],
["International Volunteer Program"] for VIE placements, ["Permanent"]).

Configure as:  source: {}   (no params needed — always fetches the full board)
"""

from __future__ import annotations

import html

import httpx

from ..models import RawPosting, clean_text, stable_id
from .base import Adapter, AdapterError

_URL = "https://recrutement.natixis.com/app/wp-json/bpce/v1/search/jobs"
_BASE_BODY = {
    "lang": "en", "keyword": "", "tax_sector": "", "tax_contract": "", "tax_place": "",
    "tax_job": "", "tax_experience": "", "tax_degree": "", "tax_brands": "",
    "tax_department": "", "tax_city": "", "tax_country": "", "tax_channel": "",
    "jobcode": "", "tax_community_job": "", "external": False, "userID": "",
}
_PAGE = 20
_MAX_PAGES = 20


class NatixisAdapter(Adapter):
    name = "natixis"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        rows: list[RawPosting] = []
        seen: set[str] = set()
        total: int | None = None
        for page in range(_MAX_PAGES):
            body = {**_BASE_BODY, "from": page * _PAGE, "size": _PAGE}
            data = await self._post_json(client, _URL, json=body)
            if not isinstance(data, dict) or "data" not in data:
                raise AdapterError(f"{self.firm.slug}: unexpected Natixis payload")
            block = data["data"]
            items = block.get("items") or []
            if page == 0:
                total = int(block.get("total") or 0)
                if not items and total:
                    raise AdapterError(f"{self.firm.slug}: Natixis returned no items for total={total}")
            new = 0
            for it in items:
                pid = clean_text(str(it.get("post_id") or it.get("job_number") or ""))
                if not pid:
                    pid = stable_id(it.get("title", ""), it.get("localisation", ""))
                if pid in seen:
                    continue
                seen.add(pid)
                new += 1
                link = (it.get("link") or {}).get("url", "")
                url = f"https://recrutement.natixis.com{link}" if link.startswith("/") else link
                contract = it.get("contract") or []
                sector = it.get("sector") or []
                job = it.get("job") or []
                rows.append(
                    RawPosting(
                        source_id=pid,
                        title=clean_text(html.unescape(it.get("title", ""))),
                        location=clean_text(it.get("localisation", "")),
                        url=url or _URL,
                        description=clean_text(html.unescape(it.get("description", "")))[:2000],
                        department=clean_text(", ".join(sector or job)),
                        employment_type=clean_text(", ".join(contract)),
                        updated_at=clean_text(it.get("date", "")),
                    )
                )
            if new == 0 or (total is not None and len(seen) >= total):
                break
        return rows
