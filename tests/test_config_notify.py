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


def test_format_events_ranks_by_comp_and_escapes_html():
    events = [
        OpeningEvent(firm="Bank", source_id="1", title="S&T Analyst <x>",
                     location="London", url="https://e.com/1", comp_k=85, comp_label="~£85k"),
        OpeningEvent(firm="Jane Street", source_id="2", title="Quant Trader",
                     location="London", url="https://e.com/2", comp_k=190, comp_label="~£190k"),
    ]
    msgs = format_events(events)
    assert len(msgs) == 1
    body = msgs[0]
    assert "2 role(s) opened" in body
    assert "&lt;x&gt;" in body  # HTML-escaped
    # higher comp listed first
    assert body.index("Jane Street") < body.index("Bank")
    assert "£190k" in body
