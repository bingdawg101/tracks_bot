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


def test_missing_token_raises():
    firm = FirmConfig(slug="acme", name="Acme", adapter="greenhouse", source={})
    with pytest.raises(AdapterError):
        # constructing is fine; fetch requires the token
        import asyncio

        async def go():
            async with httpx.AsyncClient() as client:
                await get_adapter(firm).fetch(client)

        asyncio.run(go())
