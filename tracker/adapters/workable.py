"""Workable-hosted job boards.

Public widget API, no auth:
    https://apply.workable.com/api/v1/widget/accounts/{token}?details=true

Configure as:  source: {token: example}
"""

from __future__ import annotations

import httpx

from ..models import RawPosting, clean_text
from .base import Adapter, AdapterError

BASE = "https://apply.workable.com/api/v1/widget/accounts/{token}"


class WorkableAdapter(Adapter):
    name = "workable"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        token = self._require("token")
        data = await self._get_json(client, BASE.format(token=token), params={"details": "true"})
        if not isinstance(data, dict) or "jobs" not in data:
            raise AdapterError(f"{self.firm.slug}: unexpected Workable payload")

        out: list[RawPosting] = []
        for j in data["jobs"]:
            loc = ", ".join(
                clean_text(p) for p in (j.get("city"), j.get("state"), j.get("country")) if p
            )
            out.append(
                RawPosting(
                    source_id=clean_text(j.get("shortcode", "")) or clean_text(j.get("url", "")),
                    title=clean_text(j.get("title", "")),
                    location=loc,
                    url=j.get("url", "") or j.get("application_url", ""),
                    department=clean_text(j.get("department") or j.get("function") or ""),
                    employment_type=clean_text(j.get("employment_type", "")),
                    updated_at=clean_text(j.get("published_on", "")),
                )
            )
        return out
