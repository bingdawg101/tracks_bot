"""Decide whether a posting is one the user wants to be alerted about.

Accuracy priorities, in order:
  1. Never emit a confident MATCH for an experienced-hire role. When the source gives a
     structured employment type ("Full-Time: Experienced", "Permanent", ...) it is treated
     as authoritative — description text cannot override it.
  2. Never silently drop something plausible. A posting that fits the location and shows an
     eligibility signal but whose role wording is unclear becomes REVIEW (soft alert), not IGNORE.
  3. Keyword matches are word-boundary, case-insensitive — "grad" never matches "upgrade",
     "intern" never matches "internal".
"""

from __future__ import annotations

import re
from enum import Enum

from .config import FilterConfig
from .models import MatchLevel, RawPosting, clean_text

_DEFAULT_ROLE_HINTS = (
    "trader", "trading", "quant", "quantitative", "research", "researcher",
    "sales and trading", "markets", "commodities", "commodity", "structuring", "strats",
    "execution", "market maker", "market making",
)


class _Elig(Enum):
    STRONG_YES = 3   # structured employment type says grad/intern
    TITLE_YES = 2    # eligibility term in the job title
    WEAK_YES = 1     # eligibility term only in the description
    UNKNOWN = 0
    STRONG_NO = -1   # structured employment type says experienced/permanent


def _word_hit(haystack: str, needles) -> str | None:
    low = haystack.lower()
    for n in needles:
        n = n.strip().lower()
        if not n:
            continue
        if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", low):
            return n
    return None


def _sub_hit(haystack: str, needles) -> str | None:
    low = haystack.lower()
    for n in needles:
        n = n.strip().lower()
        if n and n in low:
            return n
    return None


def _eligibility(raw: RawPosting, flt: FilterConfig) -> tuple[_Elig, str]:
    etype = clean_text(raw.employment_type)
    if etype:
        if flt.eligible_employment_types and _sub_hit(etype, flt.eligible_employment_types):
            return _Elig.STRONG_YES, f"employment type '{etype}'"
        if flt.excluded_employment_types and _sub_hit(etype, flt.excluded_employment_types):
            # Only decisive if it isn't also an eligible term (handled above).
            return _Elig.STRONG_NO, f"employment type '{etype}'"
        # Type present but unrecognised — fall through to text signals, don't guess.

    if flt.eligibility_terms:
        t = _word_hit(clean_text(raw.title), flt.eligibility_terms)
        if t:
            return _Elig.TITLE_YES, f"title mentions '{t}'"
        d = _word_hit(clean_text(raw.description), flt.eligibility_terms)
        if d:
            return _Elig.WEAK_YES, f"description mentions '{d}'"

    return _Elig.UNKNOWN, "no eligibility signal"


def classify(raw: RawPosting, flt: FilterConfig) -> tuple[MatchLevel, str]:
    """Return (level, human-readable reason)."""
    title = clean_text(raw.title)
    dept = clean_text(raw.department)
    role_field = f"{title} — {dept}"
    location = clean_text(raw.location)

    # 1. Hard excludes (word-boundary) always win.
    hit = _word_hit(role_field, flt.exclude)
    if hit:
        return MatchLevel.IGNORE, f"excluded by '{hit}'"

    # 2. Location gate.
    loc_reason = "no location filter"
    if flt.locations:
        loc_field = location or clean_text(raw.description)
        loc_hit = _sub_hit(loc_field, flt.locations)
        if not loc_hit:
            return MatchLevel.IGNORE, f"location '{location or '?'}' not in scope"
        neg = _sub_hit(loc_field, flt.location_excludes) if flt.location_excludes else None
        if neg:
            return MatchLevel.IGNORE, f"location '{location}' excluded by '{neg}'"
        loc_reason = f"location '{loc_hit}'"

    # 3. Eligibility.
    elig, elig_reason = _eligibility(raw, flt)
    if elig is _Elig.STRONG_NO:
        return MatchLevel.IGNORE, elig_reason

    # 4. Department allowlist is a HARD filter — if the user named departments, a role
    #    outside them is not for them, full stop (keeps big-bank dashboards clean).
    if flt.departments and _sub_hit(dept, flt.departments) is None:
        return MatchLevel.IGNORE, f"dept '{dept or '?'}' not in allowlist"

    # 5. Role match.
    role_hit = _word_hit(role_field, flt.include or _DEFAULT_ROLE_HINTS)
    role_ok = role_hit is not None

    # 6. Decide.
    if role_ok and elig in (_Elig.STRONG_YES, _Elig.TITLE_YES):
        return MatchLevel.MATCH, f"role '{role_hit}', {elig_reason}, {loc_reason}"

    if not flt.review_ambiguous:
        return MatchLevel.IGNORE, f"not a confident match ({elig_reason})"

    if role_ok and elig is _Elig.WEAK_YES:
        return MatchLevel.REVIEW, f"role '{role_hit}', {elig_reason} (unconfirmed), {loc_reason}"
    if role_ok and elig is _Elig.UNKNOWN:
        return MatchLevel.REVIEW, f"role '{role_hit}' but {elig_reason}, {loc_reason}"
    if not role_ok and elig in (_Elig.STRONG_YES, _Elig.TITLE_YES):
        return MatchLevel.REVIEW, f"{elig_reason}, {loc_reason}, role wording unclear"

    return MatchLevel.IGNORE, f"no role match ({elig_reason})"
