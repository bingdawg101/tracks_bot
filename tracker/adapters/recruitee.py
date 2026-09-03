"""Recruitee-hosted career sites.

Public offers API, no auth:
    https://{token}.recruitee.com/api/offers/

Configure as:  source: {token: example}
"""

from __future__ import annotations

import httpx

from ..models import RawPosting, clean_text
from .base import Adapter, AdapterError

BASE = "https://{token}.recruitee.com/api/offers/"


class RecruiteeAdapter(Adapter):
    name = "recruitee"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        token = self._require("token")
        data = await self._get_json(client, BASE.format(token=token))
        if not isinstance(data, dict) or "offers" not in data:
            raise AdapterError(f"{self.firm.slug}: unexpected Recruitee payload")

        out: list[RawPosting] = []
        for o in data["offers"]:
            if clean_text(o.get("status", "published")) not in ("published", ""):
                continue
            loc = clean_text(o.get("location") or ", ".join(
                p for p in (o.get("city"), o.get("country_code")) if p
            ))
            emp = clean_text(o.get("employment_type_code", "")).replace("_", " ")
            exp = clean_text(o.get("experience_code", "")).replace("_", " ")
            out.append(
                RawPosting(
                    source_id=str(o.get("id", "")),
                    title=clean_text(o.get("title") or o.get("position") or ""),
                    location=loc,
                    url=o.get("careers_url", "") or o.get("careers_apply_url", ""),
                    department=clean_text(o.get("department", "")),
                    employment_type=" ".join(x for x in (emp, exp) if x),
                    updated_at=clean_text(str(o.get("published_at", ""))),
                )
            )
        return out
