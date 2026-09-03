"""Teamtailor-hosted career sites.

Public JSON-Feed of jobs, no auth:
    https://{token}.teamtailor.com/jobs.json

Each item carries a schema.org JobPosting under `_jobposting`.
Configure as:  source: {token: example}   # or {host: career.example.com}
"""

from __future__ import annotations

import html

import httpx
from selectolax.parser import HTMLParser

from ..models import RawPosting, clean_text, stable_id
from .base import Adapter, AdapterError


class TeamtailorAdapter(Adapter):
    name = "teamtailor"

    def _url(self) -> str:
        host = str(self.source.get("host", "")).strip()
        if host:
            return f"https://{host}/jobs.json"
        return f"https://{self._require('token')}.teamtailor.com/jobs.json"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        data = await self._get_json(client, self._url())
        if not isinstance(data, dict) or "items" not in data:
            raise AdapterError(f"{self.firm.slug}: unexpected Teamtailor payload")

        out: list[RawPosting] = []
        for it in data["items"]:
            jp = it.get("_jobposting") or {}
            places = jp.get("jobLocation") or []
            loc = "; ".join(
                clean_text(", ".join(
                    p for p in (
                        (pl.get("address") or {}).get("addressLocality"),
                        (pl.get("address") or {}).get("addressCountry"),
                    ) if p
                ))
                for pl in places
            )
            desc = jp.get("description") or it.get("content_html") or ""
            out.append(
                RawPosting(
                    source_id=str(it.get("id") or jp.get("identifier") or stable_id(it.get("url", ""))),
                    title=clean_text(it.get("title", "")),
                    location=loc,
                    url=it.get("url", ""),
                    description=clean_text(HTMLParser(html.unescape(desc)).text(separator=" "))[:4000],
                    employment_type=clean_text(jp.get("employmentType", "")),
                    updated_at=clean_text(it.get("date_published", "")),
                )
            )
        return out
