from __future__ import annotations

from tracker.config import FilterConfig, FirmConfig, Settings
from tracker.models import OpeningEvent
from tracker.notify.telegram import format_events


def test_merged_filter_extends_default_lists():
    settings = Settings(
        defaults=FilterConfig(include=["trader"], locations=["london"]),
        firms=[FirmConfig(slug="x", name="X", adapter="greenhouse",
                          filters=FilterConfig(include=["structuring"], departments=["Markets"]))],
    )
    merged = settings.merged_filter(settings.firm("x"))
    assert set(merged.include) == {"trader", "structuring"}
    assert merged.locations == ["london"]
    assert merged.departments == ["Markets"]


def test_format_events_groups_by_firm_and_escapes_html():
    events = [
        OpeningEvent(firm="Jane Street", source_id="1", title="Quant Trader <x>",
                     location="London", url="https://e.com/1", reason="new"),
        OpeningEvent(firm="Jane Street", source_id="2", title="Quant Researcher",
                     location="London", url="https://e.com/2"),
        OpeningEvent(firm="IMC", source_id="3", title="Grad Trader", location="London"),
    ]
    msgs = format_events(events)
    assert len(msgs) == 2  # one per firm
    js = next(m for m in msgs if "Jane Street" in m)
    assert "2 role(s) opened" in js
    assert "&lt;x&gt;" in js  # title HTML-escaped
    assert 'href="https://e.com/1"' in js
