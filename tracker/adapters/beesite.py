"""BeeSite ATS (milch & zucker) — used by Deutsche Bank and others.

Public search API used by the careers front-end, no auth:
    GET https://{host}/search/?data={json}

The `data` payload selects fields and paging. Response:
    {"SearchResult": {"SearchResultCount": N, "SearchResultItems": [
        {"MatchedObjectId": "...", "MatchedObjectDescriptor": {PositionTitle, PositionURI,
         PositionLocation: [...], CareerLevel: {Name}, PositionOfferingType: {Name}, ...}}]}}

Configure as:  source: {host: api-deutschebank.beesite.de}
"""

from __future__ import annotations

import json

import httpx

from ..models import RawPosting, clean_text, stable_id
from .base import Adapter, AdapterError

_PAGE = 100
_MAX = 800

_FIELDS = [
    "PositionID", "PositionTitle", "PositionURI", "OrganizationName",
    "PositionLocation.CityName", "PositionLocation.CountryName",
    "PositionLocation.CountrySubDivisionName",
    "CareerLevel.Name", "PositionOfferingType.Name", "PositionSchedule.Name",
    "PositionFormattedDescription.Content", "PublicationStartDate", "PositionHiringYear",
]


class BeesiteAdapter(Adapter):
    name = "beesite"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        host = self._require("host")
        url = f"https://{host}/search/"

        rows: list[dict] = []
        first_item = 1
        total = None
        while True:
            payload = {
                "LanguageCode": "en",
                "SearchParameters": {
                    "FirstItem": first_item,
                    "CountItem": _PAGE,
                    "MatchedObjectDescriptor": _FIELDS,
                    "Sort": [{"Criterion": "PublicationStartDate", "Direction": "DESC"}],
                },
                "SearchCriteria": [],
            }
            data = await self._get_json(client, url, params={"data": json.dumps(payload)})
            if not isinstance(data, dict) or "SearchResult" not in data:
                raise AdapterError(f"{self.firm.slug}: unexpected BeeSite payload")
            result = data["SearchResult"] or {}
            batch = result.get("SearchResultItems") or []
            if total is None:
                total = min(
                    int(result.get("SearchResultCountAll") or result.get("SearchResultCount") or 0),
                    _MAX,
                )
            rows.extend(batch)
            first_item += _PAGE
            if first_item > total or not batch:
                break

        def _names(value) -> str:
            """BeeSite fields come as either {"Name": x} or [{"Name": x}, ...]."""
            if isinstance(value, list):
                return " ".join(clean_text(v.get("Name", "")) for v in value if isinstance(v, dict))
            if isinstance(value, dict):
                return clean_text(value.get("Name", ""))
            return ""

        out: list[RawPosting] = []
        for item in rows:
            d = item.get("MatchedObjectDescriptor") or {}
            locs = d.get("PositionLocation") or []
            loc = "; ".join(
                clean_text(", ".join(
                    p for p in (loc_.get("CityName"), loc_.get("CountryName")) if p
                ))
                for loc_ in locs
            )
            offering = _names(d.get("PositionOfferingType"))
            career = _names(d.get("CareerLevel"))
            sid = clean_text(str(item.get("MatchedObjectId") or d.get("PositionID") or "")) \
                or stable_id(d.get("PositionTitle", ""))
            out.append(
                RawPosting(
                    source_id=sid,
                    title=clean_text(d.get("PositionTitle", "")),
                    location=loc,
                    url=clean_text(d.get("PositionURI", "")),
                    description=clean_text(
                        (d.get("PositionFormattedDescription") or {}).get("Content", "")
                    )[:4000],
                    employment_type=" ".join(x for x in (offering, career) if x),
                    updated_at=clean_text(d.get("PublicationStartDate", "")),
                )
            )
        return out
