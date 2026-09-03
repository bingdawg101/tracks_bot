from __future__ import annotations

import json

import pytest

from tracker import dashboard
from tracker.config import FirmConfig, Settings
from tracker.diff import save_state
from tracker.models import FirmState, MatchLevel, Posting


@pytest.fixture(autouse=True)
def _tmp_repo(tmp_path, monkeypatch):
    monkeypatch.setattr("tracker.diff.STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(dashboard, "DOCS_DIR", tmp_path / "docs")
    monkeypatch.setattr(dashboard, "HISTORY_FILE", tmp_path / "history.json")
    (tmp_path / "history.json").write_text("[]")
    return tmp_path


def test_render_writes_html_and_json(_tmp_repo):
    st = FirmState(firm="Jane Street")
    st.tracked["1"] = Posting(firm="Jane Street", source_id="1", title="Quant Trader",
                              location="London", url="https://e.com/1",
                              employment_type="Summer Internship", match_level=MatchLevel.MATCH)
    st.tracked["2"] = Posting(firm="Jane Street", source_id="2", title="SWE",
                              location="London", match_level=MatchLevel.REVIEW)
    save_state("jane-street", st)

    settings = Settings(firms=[FirmConfig(slug="jane-street", name="Jane Street",
                                          adapter="greenhouse", source={"token": "x"})])
    dashboard.render(settings, repo="acme/tracks")

    html = (_tmp_repo / "docs" / "index.html").read_text()
    assert "Jane Street" in html and "Quant Trader" in html
    assert "acme/tracks" in html  # badge repo

    data = json.loads((_tmp_repo / "docs" / "data.json").read_text())
    assert data["total_match"] == 1
    firm = data["firms"][0]
    assert firm["match_count"] == 1 and firm["review_count"] == 1
