"""Eightfold.ai career sites (Millennium Management, and others).

Eightfold career pages ("Powered by Eightfold") expose a plain JSON search API that the
front-end itself calls — no rendering needed:

    GET https://{host}/api/apply/v2/jobs
        ?domain={domain}&location={location}&start={n}&num={page_size}

    -> {"count": N, "positions": [{id, name, location, department, ats_job_id,
        display_job_id, canonicalPositionUrl, job_description, ...}], ...}

The same JSON is also server-rendered (HTML-entity-escaped) into
`<code id="smartApplyData">...</code>` on the page itself, which is how this was found —
useful as a fallback if a given tenant ever blocks the bare API host.

Millennium runs a dedicated *campus* board on its own host (separate from the
experienced-hire board on a different Eightfold host), which is what makes this usable
for a grad/intern tracker: `campusjobs.mlp.com` only lists campus requisitions.

Configure as:
    source: {host: campusjobs.mlp.com, domain: mlp.com, location: "London, United Kingdom"}
"""

from __future__ import annotations

import httpx

from ..models import RawPosting, clean_text, stable_id
from .base import Adapter, AdapterError

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
_PAGE = 10
_MAX_PAGES = 20


class EightfoldAdapter(Adapter):
    name = "eightfold"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        host = self._require("host")
        domain = self._require("domain")
        location = str(self.source.get("location", ""))
        url = f"https://{host}/api/apply/v2/jobs"

        rows: list[RawPosting] = []
        seen: set[str] = set()
        total: int | None = None
        for page in range(_MAX_PAGES):
            params = {"domain": domain, "start": page * _PAGE, "num": _PAGE}
            if location:
                params["location"] = location
            data = await self._get_json(
                client, url, params=params, headers={"User-Agent": _UA, "Accept": "application/json"},
            )
            if not isinstance(data, dict):
                raise AdapterError(f"{self.firm.slug}: unexpected Eightfold response shape")
            positions = data.get("positions") or []
            if page == 0:
                total = int(data.get("count") or 0)
                if not positions and total:
                    raise AdapterError(f"{self.firm.slug}: Eightfold returned no positions for count={total}")
            new = 0
            for p in positions:
                jid = clean_text(str(p.get("display_job_id") or p.get("ats_job_id") or p.get("id") or ""))
                if not jid:
                    jid = stable_id(p.get("name", ""), p.get("location", ""))
                if jid in seen:
                    continue
                seen.add(jid)
                new += 1
                rows.append(
                    RawPosting(
                        source_id=jid,
                        title=clean_text(p.get("name", "")),
                        location=clean_text(p.get("location") or ""),
                        url=clean_text(p.get("canonicalPositionUrl", "")) or url,
                        description=clean_text(p.get("job_description", ""))[:2000],
                        department=clean_text(p.get("department", "")),
                        updated_at=clean_text(str(p.get("t_update", ""))),
                    )
                )
            if new == 0 or (total is not None and len(seen) >= total):
                break
        return rows
