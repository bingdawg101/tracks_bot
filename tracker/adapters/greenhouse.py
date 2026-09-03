"""Greenhouse job boards.

Public JSON, no auth:
    https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

`token` is the board slug from boards.greenhouse.io/{token} (or job-boards.greenhouse.io/{token}).
Configure as:  source: {token: janestreet}
"""

from __future__ import annotations

import html

import httpx
from selectolax.parser import HTMLParser

from ..models import RawPosting, clean_text
from .base import Adapter, AdapterError

BASE = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def _strip_html(raw: str) -> str:
    if not raw:
        return ""
    text = HTMLParser(html.unescape(raw)).text(separator=" ")
    return clean_text(text)


# Metadata field names (lowercased) that carry the grad/intern/experienced signal.
_TYPE_FIELDS = ("employment type", "job type", "worker type", "position type", "role type", "type")


def _employment_type(metadata: list[dict]) -> str:
    by_name = {
        clean_text(m.get("name", "")).lower(): clean_text(str(m.get("value") or ""))
        for m in metadata
        if m.get("value") is not None
    }
    for field in _TYPE_FIELDS:
        if by_name.get(field):
            return by_name[field]
    return ""


class GreenhouseAdapter(Adapter):
    name = "greenhouse"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        token = self._require("token")
        url = BASE.format(token=token)
        data = await self._get_json(client, url, params={"content": "true"})
        if not isinstance(data, dict) or "jobs" not in data:
            raise AdapterError(f"{self.firm.slug}: unexpected Greenhouse payload")

        postings: list[RawPosting] = []
        for job in data["jobs"]:
            depts = job.get("departments") or []
            dept = ", ".join(clean_text(d.get("name", "")) for d in depts if d.get("name"))
            metadata = job.get("metadata") or []
            postings.append(
                RawPosting(
                    source_id=str(job["id"]),
                    title=clean_text(job.get("title", "")),
                    location=clean_text((job.get("location") or {}).get("name", "")),
                    url=job.get("absolute_url", ""),
                    description=_strip_html(job.get("content", "")),
                    department=dept,
                    employment_type=_employment_type(metadata),
                    updated_at=job.get("updated_at", ""),
                    extra={
                        "metadata": {
                            clean_text(m.get("name", "")): m.get("value")
                            for m in metadata
                            if m.get("name")
                        }
                    },
                )
            )
        return postings
