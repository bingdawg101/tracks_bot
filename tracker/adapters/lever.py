"""Lever job boards.

Public JSON, no auth:
    https://api.lever.co/v0/postings/{token}?mode=json

`token` is the company slug from jobs.lever.co/{token}.
Configure as:  source: {token: example}
"""

from __future__ import annotations

import httpx

from ..models import RawPosting, clean_text
from .base import Adapter, AdapterError

BASE = "https://api.lever.co/v0/postings/{token}"


class LeverAdapter(Adapter):
    name = "lever"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        token = self._require("token")
        url = BASE.format(token=token)
        data = await self._get_json(client, url, params={"mode": "json"})
        if not isinstance(data, list):
            raise AdapterError(f"{self.firm.slug}: unexpected Lever payload")

        postings: list[RawPosting] = []
        for job in data:
            cats = job.get("categories") or {}
            postings.append(
                RawPosting(
                    source_id=str(job.get("id", "")),
                    title=clean_text(job.get("text", "")),
                    location=clean_text(cats.get("location", "")),
                    url=job.get("hostedUrl", "") or job.get("applyUrl", ""),
                    description=clean_text(job.get("descriptionPlain", "")),
                    department=clean_text(cats.get("team", "") or cats.get("department", "")),
                    employment_type=clean_text(cats.get("commitment", "")),
                    updated_at=str(job.get("createdAt", "")),
                    extra={"workType": job.get("workplaceType", "")},
                )
            )
        return postings
