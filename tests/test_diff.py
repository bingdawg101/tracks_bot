from __future__ import annotations

from tracker.diff import apply_success, record_failure
from tracker.models import FirmState, MatchLevel, Posting


def _p(sid: str, level: MatchLevel = MatchLevel.MATCH) -> Posting:
    return Posting(firm="ACME", source_id=sid, title=f"Role {sid}", location="London",
                   match_level=level, match_reason="test")


def test_first_sighting_is_baseline_and_never_alerts():
    state, events = apply_success(FirmState(firm="ACME"), "ACME", [_p("a")])
    assert events == []                       # already open when we arrived — too late
    assert state.tracked["a"].baseline is True
    assert state.established is True
    assert state.matching_ids() == {"a"}


def test_role_appearing_after_baseline_alerts_and_is_not_baseline():
    prev, _ = apply_success(FirmState(firm="ACME"), "ACME", [_p("a")])
    state, events = apply_success(prev, "ACME", [_p("a"), _p("b")])
    assert [e.source_id for e in events] == ["b"]
    assert state.tracked["b"].baseline is False
    assert state.tracked["a"].baseline is True


def test_failure_never_closes_tracked_roles():
    prev, _ = apply_success(FirmState(firm="ACME"), "ACME", [_p("a")])
    failed = record_failure(prev, "boom: 503")
    assert failed.failure_count == 1
    assert failed.matching_ids() == {"a"}
    assert failed.established is True


def test_cycle_reopening_after_all_roles_closed_alerts():
    prev, _ = apply_success(FirmState(firm="ACME"), "ACME", [_p("a")])       # baseline
    closed, events = apply_success(prev, "ACME", [])                          # all roles gone
    assert events == [] and closed.matching_ids() == set()
    assert closed.established is True
    reopened, events = apply_success(closed, "ACME", [_p("c")])               # cycle reopens
    assert [e.source_id for e in events] == ["c"]
    assert "0 to 1" in events[0].reason
    assert reopened.tracked["c"].baseline is False


def test_review_promoted_to_match_alerts_only_if_not_baseline():
    # a review that was there at baseline, later promoted -> not a fresh opening
    prev, _ = apply_success(FirmState(firm="ACME"), "ACME", [_p("a", MatchLevel.REVIEW)])
    state, events = apply_success(prev, "ACME", [_p("a", MatchLevel.MATCH)])
    assert events == []

    # a review that appeared while watching, then promoted -> alert
    p2, _ = apply_success(state, "ACME", [_p("a", MatchLevel.MATCH), _p("b", MatchLevel.REVIEW)])
    p3, events = apply_success(p2, "ACME", [_p("a", MatchLevel.MATCH), _p("b", MatchLevel.MATCH)])
    assert [e.source_id for e in events] == ["b"]
