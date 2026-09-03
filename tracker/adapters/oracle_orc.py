"""Oracle Recruiting Cloud (ORC) "Candidate Experience" career sites.

Public REST API used by the CE front-end, no auth:
    GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
        ?onlyData=true
        &expand=requisitionList.workLocation,requisitionList.secondaryLocations
        &finder=findReqs;siteNumber={site},limit=200,offset=0,sortBy=POSTING_DATES_DESC

Used by JPMorgan (jpmc.fa.oraclecloud.com / CX_1001) and others.
Configure as:  source: {host: jpmc.fa.oraclecloud.com, site: CX_1001}
"""

from __future__ import annotations

import httpx

from ..models import RawPosting, clean_text
from .base import Adapter, AdapterError

_PAGE = 200
# Cap total rows. Sorted newest-first, so a freshly-opened role is always within the cap —
# which is exactly what we're watching for. Big banks post thousands of roles globally.
_MAX = 1200
_PATH = "/hcmRestApi/resources/latest/recruitingCEJobRequisitions"


class OracleOrcAdapter(Adapter):
    name = "oracle_orc"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        host = self._require("host")
        site = self._require("site")
        url = f"https://{host}{_PATH}"

        rows: list[dict] = []
        total = None
        offset = 0
        while True:
            finder = (
                f"findReqs;siteNumber={site},limit={_PAGE},offset={offset},"
                "sortBy=POSTING_DATES_DESC"
            )
            data = await self._get_json(
                client, url,
                params={
                    "onlyData": "true",
                    "expand": "requisitionList.workLocation,requisitionList.secondaryLocations",
                    "finder": finder,
                },
            )
            try:
                block = data["items"][0]
            except (KeyError, IndexError, TypeError):
                raise AdapterError(f"{self.firm.slug}: unexpected Oracle ORC payload") from None
            batch = block.get("requisitionList", []) or []
            rows.extend(batch)
            if total is None:
                total = min(int(block.get("TotalJobsCount", len(batch))), _MAX)
            offset += _PAGE
            if offset >= total or not batch:
                break

        base = f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/"
        out: list[RawPosting] = []
        for r in rows:
            loc = clean_text(r.get("PrimaryLocation", ""))
            secondary = r.get("secondaryLocations") or []
            if secondary:
                loc += "; " + "; ".join(
                    clean_text(s.get("Name", "")) for s in secondary if s.get("Name")
                )
            out.append(
                RawPosting(
                    source_id=str(r.get("Id", "")),
                    title=clean_text(r.get("Title", "")),
                    location=loc,
                    url=base + str(r.get("Id", "")),
                    department=clean_text(r.get("JobFunction", "")),
                    employment_type=clean_text(r.get("WorkerType", "")),
                    updated_at=clean_text(r.get("PostedDate", "")),
                )
            )
        return out
