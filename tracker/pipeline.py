"""Orchestrate one tracking run: fetch -> classify -> diff -> notify -> persist."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import httpx

from .adapters import AdapterError, get_adapter
from .config import HISTORY_FILE, Settings
from .diff import apply_success, load_state, record_failure, save_state, snapshot_raw
from .filters import classify
from .models import MatchLevel, OpeningEvent, Posting, RawPosting, utcnow
from .notify import TelegramNotifier

_USER_AGENT = (
    "careers-tracker/0.1 (+https://github.com/) personal job-opening monitor"
)


@dataclass
class FirmResult:
    slug: str
    name: str
    ok: bool
    events: list[OpeningEvent] = field(default_factory=list)
    matched: list[Posting] = field(default_factory=list)
    review: list[Posting] = field(default_factory=list)
    error: str = ""
    failure_count: int = 0


@dataclass
class RunResult:
    results: list[FirmResult]
    started_at: str

    @property
    def events(self) -> list[OpeningEvent]:
        return [e for r in self.results for e in r.events]

    @property
    def unhealthy(self) -> list[FirmResult]:
        return [r for r in self.results if not r.ok]


def _classify_all(firm_name: str, raws: list[RawPosting], flt) -> list[Posting]:
    out: list[Posting] = []
    for raw in raws:
        level, reason = classify(raw, flt)
        out.append(
            Posting(
                firm=firm_name,
                source_id=raw.source_id,
                title=raw.title,
                location=raw.location,
                url=raw.url,
                department=raw.department,
                employment_type=raw.employment_type,
                match_level=level,
                match_reason=reason,
            )
        )
    return out


async def _process_firm(
    firm, settings: Settings, client: httpx.AsyncClient, *, persist: bool
) -> FirmResult:
    prev = load_state(firm.slug, firm.name)
    flt = settings.merged_filter(firm)
    budget = float(firm.source.get("timeout", settings.firm_timeout_seconds))
    try:
        adapter = get_adapter(firm)
        raws = await asyncio.wait_for(adapter.fetch(client), timeout=budget)
    except (AdapterError, httpx.HTTPError, TimeoutError) as exc:
        msg = f"timed out after {budget:.0f}s" if isinstance(exc, TimeoutError) else str(exc)
        new_state = record_failure(prev, msg)
        if persist:
            save_state(firm.slug, new_state)
        return FirmResult(
            slug=firm.slug, name=firm.name, ok=False,
            error=msg, failure_count=new_state.failure_count,
        )

    postings = _classify_all(firm.name, raws, flt)
    new_state, events = apply_success(prev, firm.name, postings)

    matched = [p for p in postings if p.match_level == MatchLevel.MATCH]
    review = [p for p in postings if p.match_level == MatchLevel.REVIEW]

    if persist:
        # Snapshot raw payload only when the tracked set changed, for audit.
        if {p.source_id for p in matched + review} != set(prev.tracked):
            snapshot_raw(firm.slug, [r.model_dump() for r in raws])
        save_state(firm.slug, new_state)

    return FirmResult(
        slug=firm.slug, name=firm.name, ok=True, events=events,
        matched=matched, review=review, failure_count=0,
    )


async def run(
    settings: Settings,
    *,
    only: list[str] | None = None,
    persist: bool = True,
    dry_run: bool = False,
    seed: bool = False,
    notifier: TelegramNotifier | None = None,
) -> RunResult:
    # seed: establish the baseline for (new) firms — persist state, but emit no history
    # entries and no alerts for what's already open.
    firms = settings.enabled_firms()
    if only:
        wanted = set(only)
        firms = [f for f in firms if f.slug in wanted]

    started = utcnow().isoformat()
    sem = asyncio.Semaphore(settings.max_concurrency)
    limits = httpx.Limits(max_connections=settings.max_concurrency)
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}

    async with httpx.AsyncClient(
        timeout=settings.http_timeout_seconds, headers=headers, limits=limits,
        follow_redirects=True,
    ) as client:

        async def guarded(f):
            async with sem:
                return await _process_firm(f, settings, client, persist=persist)

        results = await asyncio.gather(*(guarded(f) for f in firms))

    run_result = RunResult(results=list(results), started_at=started)

    events = run_result.events
    if events and persist and not seed:
        _append_history(events)
    if events and notifier and not dry_run and not seed:
        await notifier.send_events(events)

    return run_result


def _append_history(events: list[OpeningEvent]) -> None:
    existing: list[dict] = []
    if HISTORY_FILE.exists():
        try:
            existing = json.loads(HISTORY_FILE.read_text())
        except json.JSONDecodeError:
            existing = []
    existing.extend(json.loads(e.model_dump_json()) for e in events)
    HISTORY_FILE.write_text(json.dumps(existing, indent=2))
