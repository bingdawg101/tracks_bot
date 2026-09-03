from __future__ import annotations

from tracker.filters import classify
from tracker.models import MatchLevel, RawPosting


def _raw(**kw) -> RawPosting:
    base = {"source_id": "1", "title": "", "location": "London, United Kingdom"}
    base.update(kw)
    return RawPosting(**base)


def test_structured_intern_type_is_a_match(flt):
    raw = _raw(title="Quantitative Trader", department="Quantitative Trading",
              employment_type="Summer Internship")
    level, reason = classify(raw, flt)
    assert level is MatchLevel.MATCH
    assert "Summer Internship" in reason


def test_experienced_type_overrides_description_text(flt):
    # Description mentions "internship" but the structured type is authoritative.
    raw = _raw(title="Quantitative Trader", employment_type="Full-Time: Experienced",
              description="You will mentor our summer internship cohort.")
    level, _ = classify(raw, flt)
    assert level is MatchLevel.IGNORE


def test_title_eligibility_without_structured_type(flt):
    raw = _raw(title="Graduate Quantitative Researcher, London")
    level, _ = classify(raw, flt)
    assert level is MatchLevel.MATCH


def test_word_boundary_intern_does_not_match_internal(flt):
    raw = _raw(title="Internal Audit Analyst",
              description="Work with internal stakeholders across the firm.")
    level, _ = classify(raw, flt)
    assert level is MatchLevel.IGNORE


def test_word_boundary_grad_does_not_match_upgrade(flt):
    # "upgrades" must not register as the eligibility term "grad"; with no role hit either
    # this is a clean IGNORE.
    raw = _raw(title="Platform Reliability Engineer",
              description="Responsible for upgrades to the deployment stack.")
    level, reason = classify(raw, flt)
    assert level is MatchLevel.IGNORE
    assert "no role match" in reason


def test_location_gate_rejects_out_of_scope(flt):
    raw = _raw(title="Graduate Quantitative Trader", location="New York, NY")
    level, _ = classify(raw, flt)
    assert level is MatchLevel.IGNORE


def test_ambiguous_role_with_strong_eligibility_is_review(flt):
    raw = _raw(title="Software Engineer", employment_type="Summer Internship")
    level, _ = classify(raw, flt)
    assert level is MatchLevel.REVIEW


def test_role_match_but_no_eligibility_is_review(flt):
    raw = _raw(title="Quantitative Trader")
    level, _ = classify(raw, flt)
    assert level is MatchLevel.REVIEW


def test_exclude_term_wins(flt):
    raw = _raw(title="Senior Quantitative Trader", employment_type="Summer Internship")
    level, reason = classify(raw, flt)
    assert level is MatchLevel.IGNORE
    assert "senior" in reason


def test_department_allowlist_is_a_hard_filter(flt):
    scoped = flt.model_copy(update={"departments": ["Quantitative Trading"]})
    off = _raw(title="Quantitative Researcher", department="Cybersecurity",
               employment_type="Summer Internship")
    assert classify(off, scoped)[0] is MatchLevel.IGNORE
    on = _raw(title="Quantitative Trader", department="Quantitative Trading",
              employment_type="Summer Internship")
    assert classify(on, scoped)[0] is MatchLevel.MATCH
