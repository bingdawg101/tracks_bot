"""Core data types shared across adapters, filters, diff and notifications."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    """Timezone-aware UTC now. Always use this, never datetime.utcnow()."""
    return datetime.now(UTC)


class MatchLevel(str, Enum):
    """How confident we are that a posting is one the user cares about."""

    MATCH = "match"          # in-scope role, right location, grad/intern eligible -> alert
    REVIEW = "review"        # location + eligibility fit but role wording is ambiguous
    IGNORE = "ignore"        # not relevant


class RawPosting(BaseModel):
    """What an adapter returns before normalisation/filtering.

    Adapters should populate as many fields as the source exposes. `source_id` must be
    stable across runs for the same underlying requisition — prefer the ATS's own id.
    """

    source_id: str
    title: str
    location: str = ""
    url: str = ""
    description: str = ""          # plain text where available, used for eligibility detection
    department: str = ""
    employment_type: str = ""      # structured type from source ("Summer Internship", "Intern", ...)
    updated_at: str = ""           # source's own timestamp string, informational only
    extra: dict = Field(default_factory=dict)


class Posting(BaseModel):
    """A normalised posting attached to a firm, with the match decision recorded."""

    firm: str
    source_id: str
    title: str
    location: str = ""
    url: str = ""
    department: str = ""
    employment_type: str = ""
    match_level: MatchLevel = MatchLevel.IGNORE
    match_reason: str = ""
    first_seen: datetime = Field(default_factory=utcnow)

    @property
    def key(self) -> str:
        """Stable identity for diffing: firm + source id."""
        return f"{self.firm}::{self.source_id}"

    def summary_line(self) -> str:
        loc = f" — {self.location}" if self.location else ""
        return f"{self.title}{loc}"


_WS = re.compile(r"\s+")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return _WS.sub(" ", value).strip()


def stable_id(*parts: str) -> str:
    """Deterministic id from arbitrary parts, for sources with no usable id of their own."""
    joined = "|".join(clean_text(p).lower() for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


class FirmState(BaseModel):
    """Persisted per-firm state, committed back to the repo each run."""

    firm: str
    last_run: datetime | None = None
    last_success: datetime | None = None
    failure_count: int = 0
    last_error: str = ""
    # source_id -> serialised Posting for everything currently matching (MATCH or REVIEW)
    tracked: dict[str, Posting] = Field(default_factory=dict)

    def matching_ids(self) -> set[str]:
        return {
            sid for sid, p in self.tracked.items() if p.match_level == MatchLevel.MATCH
        }


class OpeningEvent(BaseModel):
    """One detected opening, appended to history.json and sent as an alert."""

    firm: str
    source_id: str
    title: str
    location: str = ""
    url: str = ""
    match_level: MatchLevel = MatchLevel.MATCH
    detected_at: datetime = Field(default_factory=utcnow)
    reason: str = ""
