"""Ashby-hosted job boards.

Public posting API, no auth:
    https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true

Configure as:  source: {token: example}
"""

from __future__ import annotations

import httpx

from ..models import RawPosting, clean_text
from .base import Adapter, AdapterError

BASE = "https://api.ashbyhq.com/posting-api/job-board/{token}"


class AshbyAdapter(Adapter):
    name = "ashby"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        token = self._require("token")
        data = await self._get_json(client, BASE.format(token=token))
        if not isinstance(data, dict) or "jobs" not in data:
            raise AdapterError(f"{self.firm.slug}: unexpected Ashby payload")

        out: list[RawPosting] = []
        for j in data["jobs"]:
            out.append(
                RawPosting(
                    source_id=str(j.get("id", "")),
                    title=clean_text(j.get("title", "")),
                    location=clean_text(j.get("location", "")),
                    url=j.get("jobUrl", "") or j.get("applyUrl", ""),
                    department=clean_text(j.get("department", "") or j.get("team", "")),
                    employment_type=clean_text(j.get("employmentType", "")),
                    updated_at=clean_text(j.get("publishedAt", "")),
                )
            )
        return out
