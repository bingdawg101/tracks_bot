"""SmartRecruiters-hosted career sites.

Public Posting API, no auth:
    https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=100&offset=0

Configure as:  source: {company: Vitol}
"""

from __future__ import annotations

import httpx

from ..models import RawPosting, clean_text
from .base import Adapter, AdapterError

BASE = "https://api.smartrecruiters.com/v1/companies/{company}/postings"
_PAGE = 100


class SmartRecruitersAdapter(Adapter):
    name = "smartrecruiters"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        company = self._require("company")
        url = BASE.format(company=company)
        rows: list[dict] = []
        offset = 0
        while True:
            data = await self._get_json(client, url, params={"limit": _PAGE, "offset": offset})
            if not isinstance(data, dict) or "content" not in data:
                raise AdapterError(f"{self.firm.slug}: unexpected SmartRecruiters payload")
            batch = data["content"]
            rows.extend(batch)
            offset += _PAGE
            if offset >= int(data.get("totalFound", 0)) or not batch:
                break

        out: list[RawPosting] = []
        for j in rows:
            loc = j.get("location") or {}
            loc_str = ", ".join(
                p for p in (loc.get("city"), loc.get("region"), loc.get("country", "").upper())
                if p
            )
            emp = clean_text((j.get("typeOfEmployment") or {}).get("label", ""))
            exp = clean_text((j.get("experienceLevel") or {}).get("label", ""))
            out.append(
                RawPosting(
                    source_id=str(j.get("id", "")),
                    title=clean_text(j.get("name", "")),
                    location=clean_text(loc_str),
                    url=f"https://jobs.smartrecruiters.com/{company}/{j.get('id')}",
                    department=clean_text((j.get("department") or {}).get("label", "")),
                    # SR splits the signal across two fields — combine so the classifier sees both
                    # ("Internship", "Entry Level", "Mid-Senior Level", ...).
                    employment_type=" ".join(x for x in (emp, exp) if x),
                    updated_at=clean_text(j.get("releasedDate", "")),
                )
            )
        return out
