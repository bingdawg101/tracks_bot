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
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"


class WorkableAdapter(Adapter):
    name = "workable"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        # apply.workable.com rate-limits hard by IP (429/CF-1015). Extra retries help; a
        # persistent 429 is treated as transient by the health check, not a real breakage.
        token = self._require("token")
        data = await self._get_json(
            client, BASE.format(token=token),
            params={"details": "true"}, headers={"User-Agent": _UA}, retries=3,
        )
        if not isinstance(data, dict) or "jobs" not in data:
            raise AdapterError(f"{self.firm.slug}: unexpected Workable payload")

        out: list[RawPosting] = []
        for j in data["jobs"]:
            loc_obj = j.get("location") if isinstance(j.get("location"), dict) else {}
            loc = ", ".join(
                clean_text(p) for p in (
                    j.get("city") or loc_obj.get("city"),
                    j.get("state") or loc_obj.get("region"),
                    j.get("country") or loc_obj.get("country"),
                ) if p
            )
            out.append(
                RawPosting(
                    source_id=clean_text(j.get("shortcode") or str(j.get("id", "")))
                    or clean_text(j.get("url", "")),
                    title=clean_text(j.get("title", "")),
                    location=loc,
                    url=j.get("url", "") or j.get("application_url", "") or j.get("shortlink", ""),
                    department=clean_text(j.get("department") or j.get("function") or ""),
                    employment_type=clean_text(j.get("employment_type", "")),
                    updated_at=clean_text(j.get("published_on") or j.get("created_at") or ""),
                )
            )
        return out
