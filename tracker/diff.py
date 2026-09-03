"""Per-firm state persistence and opening detection.

Accuracy rules baked in here:
  * A fetch failure NEVER mutates the tracked set — closure is only inferred from a
    successful fetch that omits a previously-seen posting.
  * An opening fires when a MATCH posting id is newly present, OR when the firm goes
    from zero MATCH postings to at least one (covers re-labelled requisitions).
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import RAW_DIR, STATE_DIR
from .models import FirmState, MatchLevel, OpeningEvent, Posting, utcnow

_RAW_KEEP = 5


def state_path(slug: str) -> Path:
    return STATE_DIR / f"{slug}.json"


def load_state(slug: str, firm_name: str) -> FirmState:
    path = state_path(slug)
    if not path.exists():
        return FirmState(firm=firm_name)
    return FirmState.model_validate_json(path.read_text())


def save_state(slug: str, state: FirmState) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    # `match_reason` is a derived explanation regenerated every run — persisting it would
    # churn the whole file whenever filter wording changes. Keep it out of state.
    state_path(slug).write_text(
        state.model_dump_json(indent=2, exclude={"tracked": {"__all__": {"match_reason"}}})
    )


def record_failure(state: FirmState, error: str) -> FirmState:
    state.failure_count += 1
    state.last_error = error
    return state


def apply_success(
    prev: FirmState,
    firm_name: str,
    postings: list[Posting],
) -> tuple[FirmState, list[OpeningEvent]]:
    """Compute the new state and any openings, given a successful fetch's classified postings."""
    now = utcnow()
    # Sort by source_id so the serialised file is order-stable regardless of the order
    # the source returned postings in — otherwise every run produces a spurious diff.
    tracked_now = {
        p.source_id: p
        for p in sorted(postings, key=lambda x: x.source_id)
        if p.match_level in (MatchLevel.MATCH, MatchLevel.REVIEW)
    }

    prev_match_ids = prev.matching_ids()
    prev_review_ids = {
        sid for sid, p in prev.tracked.items() if p.match_level == MatchLevel.REVIEW
    }
    new_match_ids = {sid for sid, p in tracked_now.items() if p.match_level == MatchLevel.MATCH}

    events: list[OpeningEvent] = []

    # Carry first_seen forward for postings we already knew about.
    for sid, p in tracked_now.items():
        if sid in prev.tracked:
            p.first_seen = prev.tracked[sid].first_seen

    firm_reopened = not prev_match_ids and new_match_ids

    for sid in sorted(new_match_ids):
        p = tracked_now[sid]
        is_new = sid not in prev_match_ids
        if not is_new:
            continue
        reason = p.match_reason
        if firm_reopened and not prev.tracked:
            reason = f"first matching role seen for firm — {reason}"
        elif firm_reopened:
            reason = f"firm went from 0 to {len(new_match_ids)} matching roles — {reason}"
        elif sid in prev_review_ids:
            reason = f"promoted from review to match — {reason}"
        events.append(
            OpeningEvent(
                firm=firm_name,
                source_id=sid,
                title=p.title,
                location=p.location,
                url=p.url,
                match_level=MatchLevel.MATCH,
                detected_at=now,
                reason=reason,
            )
        )

    new_state = FirmState(
        firm=firm_name,
        failure_count=0,
        last_error="",
        tracked=tracked_now,
    )
    return new_state, events


def snapshot_raw(slug: str, payload: object) -> None:
    """Keep the last few raw adapter payloads for auditing a questionable alert."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().strftime("%Y%m%dT%H%M%SZ")
    (RAW_DIR / f"{slug}-{stamp}.json").write_text(
        json.dumps(payload, indent=2, default=str)
    )
    existing = sorted(RAW_DIR.glob(f"{slug}-*.json"))
    for stale in existing[:-_RAW_KEEP]:
        stale.unlink(missing_ok=True)
