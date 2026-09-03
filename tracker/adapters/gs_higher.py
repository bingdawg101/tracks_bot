"""Goldman Sachs — higher.gs.com.

GS runs its own recruiting platform. The front-end calls an unauthenticated GraphQL
gateway; `roleSearch` returns early-career / campus roles.

    POST https://api-higher.gs.com/gateway/api/v1/graphql

No config needed:  adapter: gs_higher   (source may set `experiences` to override).
Default experiences: EARLY_CAREER, CAMPUS.
"""

from __future__ import annotations

import httpx

from ..models import RawPosting, clean_text
from .base import Adapter, AdapterError

_URL = "https://api-higher.gs.com/gateway/api/v1/graphql"
_PAGE = 100
_QUERY = """
query RoleSearch($in: RoleSearchQueryInput!) {
  roleSearch(searchQueryInput: $in) {
    totalCount
    items {
      roleId jobTitle division jobFunction corporateTitle externalJobStatus
      educationLevel lastPostedDate
      jobType { code description }
      locations { city country primary }
    }
  }
}
"""


class GsHigherAdapter(Adapter):
    name = "gs_higher"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        experiences = self.source.get("experiences") or ["EARLY_CAREER", "CAMPUS"]

        rows: list[dict] = []
        page = 0
        while True:
            payload = {
                "query": _QUERY,
                "variables": {
                    "in": {
                        "page": {"pageSize": _PAGE, "pageNumber": page},
                        "experiences": experiences,
                        "searchTerm": "",
                    }
                },
            }
            data = await self._post_json(client, _URL, json=payload)
            if not isinstance(data, dict) or "data" not in data or data.get("errors"):
                raise AdapterError(f"{self.firm.slug}: GS GraphQL error: {data.get('errors')}")
            block = data["data"]["roleSearch"]
            batch = block.get("items") or []
            rows.extend(batch)
            page += 1
            if page * _PAGE >= int(block.get("totalCount", 0)) or not batch:
                break

        out: list[RawPosting] = []
        for r in rows:
            locs = r.get("locations") or []
            loc_str = "; ".join(
                clean_text(f"{loc_.get('city', '')} {loc_.get('country', '')}".strip())
                for loc_ in locs
            )
            jt = (r.get("jobType") or {}).get("description", "")
            out.append(
                RawPosting(
                    source_id=str(r.get("roleId", "")),
                    title=clean_text(r.get("jobTitle", "").replace(" | ", " / ")),
                    location=loc_str,
                    url=f"https://higher.gs.com/roles/{r.get('roleId')}",
                    department=clean_text(r.get("division", "") or r.get("jobFunction", "")),
                    # "Summer Analyst", "Internship", "Off-Cycle" all live in jobType/title here
                    employment_type=clean_text(f"{jt} {r.get('educationLevel') or ''}"),
                    updated_at=clean_text(r.get("lastPostedDate", "")),
                )
            )
        return out
