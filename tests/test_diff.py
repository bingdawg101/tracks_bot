from __future__ import annotations

from tracker.diff import apply_success, record_failure
from tracker.models import FirmState, MatchLevel, Posting


def _p(sid: str, level: MatchLevel = MatchLevel.MATCH) -> Posting:
    return Posting(firm="ACME", source_id=sid, title=f"Role {sid}", location="London",
                   match_level=level, match_reason="test")


def test_first_match_emits_opening():
    prev = FirmState(firm="ACME")
    state, events = apply_success(prev, "ACME", [_p("a")])
    assert [e.source_id for e in events] == ["a"]
    assert state.matching_ids() == {"a"}
    assert state.failure_count == 0


def test_known_posting_does_not_re_alert():
    prev, _ = apply_success(FirmState(firm="ACME"), "ACME", [_p("a")])
    state, events = apply_success(prev, "ACME", [_p("a"), _p("b")])
    assert [e.source_id for e in events] == ["b"]
    assert state.matching_ids() == {"a", "b"}


def test_failure_never_closes_tracked_roles():
    prev, _ = apply_success(FirmState(firm="ACME"), "ACME", [_p("a")])
    failed = record_failure(prev, "boom: 503")
    assert failed.failure_count == 1
    assert failed.last_error == "boom: 503"
    assert failed.matching_ids() == {"a"}  # unchanged


def test_reopen_after_all_roles_closed_emits_opening():
    prev, _ = apply_success(FirmState(firm="ACME"), "ACME", [_p("a")])
    closed, events = apply_success(prev, "ACME", [])  # successful fetch, nothing matching
    assert events == []
    assert closed.matching_ids() == set()
    reopened, events = apply_success(closed, "ACME", [_p("c")])
    assert [e.source_id for e in events] == ["c"]
    assert "0 to 1" in events[0].reason or "first matching" in events[0].reason


def test_review_promoted_to_match_emits_opening():
    prev, _ = apply_success(FirmState(firm="ACME"), "ACME", [_p("a", MatchLevel.REVIEW)])
    assert prev.matching_ids() == set()
    state, events = apply_success(prev, "ACME", [_p("a", MatchLevel.MATCH)])
    assert [e.source_id for e in events] == ["a"]
