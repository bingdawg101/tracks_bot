from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from tracker.adapters import get_adapter
from tracker.adapters.base import AdapterError
from tracker.config import FirmConfig

FIX = Path(__file__).parent / "fixtures"


@respx.mock
async def test_greenhouse_parses_metadata_and_html():
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").mock(
        return_value=httpx.Response(200, json=json.loads((FIX / "greenhouse_sample.json").read_text()))
    )
    firm = FirmConfig(slug="acme", name="Acme", adapter="greenhouse", source={"token": "acme"})
    async with httpx.AsyncClient() as client:
        postings = await get_adapter(firm).fetch(client)

    assert len(postings) == 2
    intern = next(p for p in postings if p.source_id == "111")
    assert intern.employment_type == "Summer Internship"
    assert intern.department == "Quantitative Trading"
    assert "pricing inefficiencies" in intern.description
    assert "<" not in intern.description


@respx.mock
async def test_lever_maps_commitment_to_employment_type():
    respx.get("https://api.lever.co/v0/postings/acme").mock(
        return_value=httpx.Response(200, json=json.loads((FIX / "lever_sample.json").read_text()))
    )
    firm = FirmConfig(slug="acme", name="Acme", adapter="lever", source={"token": "acme"})
    async with httpx.AsyncClient() as client:
        postings = await get_adapter(firm).fetch(client)

    assert len(postings) == 1
    assert postings[0].employment_type == "Intern"
    assert postings[0].location == "London, UK"


@respx.mock
async def test_http_error_becomes_adapter_error():
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").mock(
        return_value=httpx.Response(500)
    )
    firm = FirmConfig(slug="acme", name="Acme", adapter="greenhouse", source={"token": "acme"})
    async with httpx.AsyncClient() as client:
        with pytest.raises(AdapterError):
            await get_adapter(firm).fetch(client)


@respx.mock
async def test_smartrecruiters_combines_type_and_experience():
    payload = {
        "totalFound": 1,
        "content": [{
            "id": "77", "name": "Graduate Trader",
            "location": {"city": "London", "country": "gb"},
            "department": {"label": "Trading"},
            "typeOfEmployment": {"label": "Full-time"},
            "experienceLevel": {"label": "Internship"},
            "releasedDate": "2026-09-01",
        }],
    }
    respx.get("https://api.smartrecruiters.com/v1/companies/Acme/postings").mock(
        return_value=httpx.Response(200, json=payload)
    )
    firm = FirmConfig(slug="acme", name="Acme", adapter="smartrecruiters", source={"company": "Acme"})
    async with httpx.AsyncClient() as client:
        p = (await get_adapter(firm).fetch(client))[0]
    assert p.employment_type == "Full-time Internship"
    assert "London" in p.location


@respx.mock
async def test_workday_applies_uk_country_facet():
    unfiltered = {
        "total": 999, "jobPostings": [],
        "facets": [{"facetParameter": "Location_Country", "values": [
            {"id": "uk-id", "descriptor": "United Kingdom"},
            {"id": "us-id", "descriptor": "United States of America"},
        ]}],
    }
    uk_page = {"total": 1, "jobPostings": [{
        "title": "2027 Sales & Trading Analyst Programme", "externalPath": "/job/London/x_R123",
        "bulletFields": ["R123"], "locationsText": "London", "postedOn": "Posted Today",
    }]}
    route = respx.post("https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/External/jobs")
    route.side_effect = [
        httpx.Response(200, json=unfiltered),
        httpx.Response(200, json=uk_page),
    ]
    firm = FirmConfig(slug="acme", name="Acme", adapter="workday",
                      source={"tenant": "acme", "wd": "wd3", "site": "External"})
    async with httpx.AsyncClient() as client:
        posts = await get_adapter(firm).fetch(client)
    assert len(posts) == 1
    assert posts[0].source_id == "R123"
    assert posts[0].url.endswith("/job/London/x_R123")
    # second request carried the UK facet
    sent = route.calls[1].request
    assert b"uk-id" in sent.content and b"us-id" not in sent.content


@respx.mock
async def test_oracle_orc_paginates_and_flattens_locations():
    def block(items, total):
        return {"items": [{"TotalJobsCount": total, "requisitionList": items}]}
    respx.get(
        "https://acme.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    ).mock(return_value=httpx.Response(200, json=block(
        [{"Id": "1", "Title": "Markets Summer Analyst", "PrimaryLocation": "London",
          "PostedDate": "2026-09-02", "JobFunction": "Markets",
          "secondaryLocations": [{"Name": "Glasgow"}]}], 1)))
    firm = FirmConfig(slug="acme", name="Acme", adapter="oracle_orc",
                      source={"host": "acme.fa.oraclecloud.com", "site": "CX_1001"})
    async with httpx.AsyncClient() as client:
        p = (await get_adapter(firm).fetch(client))[0]
    assert p.location == "London; Glasgow"
    assert p.source_id == "1"


def test_missing_token_raises():
    firm = FirmConfig(slug="acme", name="Acme", adapter="greenhouse", source={})
    with pytest.raises(AdapterError):
        # constructing is fine; fetch requires the token
        import asyncio

        async def go():
            async with httpx.AsyncClient() as client:
                await get_adapter(firm).fetch(client)

        asyncio.run(go())
