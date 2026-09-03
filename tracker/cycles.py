"""Curated recruiting-cycle registry.

The tracker's real value is catching a cycle the day it opens — a role that is already
open when we first see it is usually too late. This registry records, per firm, when each
graduate / summer / off-cycle programme is *expected* to open (from published dates and
prior-year patterns), so the dashboard can show a "what opens next" calendar and the
alerts can shout when a not-yet-open cycle flips to open.

Populated in `firms.yaml` under `cycles:` (slug -> list of entries).
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel

from .models import utcnow


class CycleStatus:
    NOT_YET_OPEN = "not_yet_open"
    OPEN = "open"
    ROLLING = "rolling"           # applications accepted year-round
    CLOSED = "closed"             # cycle done, will reopen next year
    UNKNOWN = "unknown"


class Cycle(BaseModel):
    programme: str = "Graduate / Internship"
    status: str = CycleStatus.UNKNOWN
    # Expected/actual open — an ISO date, a month "2026-09", a window "2026-09..2026-10",
    # or "rolling". `closes` is the application deadline if known.
    opens: str = ""
    closes: str = ""
    year: int = 0                 # the cohort year, e.g. 2027 for "Summer 2027"
    source: str = ""
    notes: str = ""

    def open_window(self) -> tuple[date | None, date | None]:
        """(earliest, latest) plausible open dates; (None, None) if unknown/rolling."""
        return _parse_window(self.opens)

    def days_until_open(self, ref: date | None = None) -> int | None:
        ref = ref or utcnow().date()
        earliest, latest = self.open_window()
        target = earliest or latest
        return (target - ref).days if target else None

    def opens_display(self) -> str:
        if self.status == CycleStatus.ROLLING or self.opens.lower() == "rolling":
            return "rolling"
        earliest, latest = self.open_window()
        if earliest and latest and earliest != latest:
            return f"{earliest:%b %Y}"
        if earliest:
            return f"{earliest:%d %b %Y}" if "-" in self.opens and self.opens.count("-") == 2 \
                else f"{earliest:%b %Y}"
        return self.opens or "?"


_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _one(token: str) -> date | None:
    token = token.strip()
    m = _DATE.match(token)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = _MONTH.match(token)
    if m:
        return date(int(m[1]), int(m[2]), 1)
    return None


def _parse_window(spec: str) -> tuple[date | None, date | None]:
    spec = (spec or "").strip().lower()
    if not spec or spec == "rolling":
        return (None, None)
    if ".." in spec:
        a, b = spec.split("..", 1)
        return (_one(a), _one(b))
    d = _one(spec)
    if d and _MONTH.match(spec):
        # a bare month → window spanning that month
        nxt = date(d.year + (d.month == 12), (d.month % 12) + 1, 1)
        return (d, nxt)
    return (d, d)


def upcoming(cycles_by_firm: dict[str, list[Cycle]], within_days: int = 120,
             firm_names: dict[str, str] | None = None) -> list[dict]:
    """Flattened, date-sorted list of cycles expected to open within `within_days`."""
    names = firm_names or {}
    now = utcnow().date()
    rows: list[dict] = []
    for slug, cycles in cycles_by_firm.items():
        for cyc in cycles:
            if cyc.status not in (CycleStatus.NOT_YET_OPEN, CycleStatus.UNKNOWN):
                continue
            dleft = cyc.days_until_open(now)
            if dleft is None or dleft < -14 or dleft > within_days:
                continue
            rows.append({
                "slug": slug,
                "firm": names.get(slug, slug),
                "programme": cyc.programme,
                "opens_display": cyc.opens_display(),
                "days_until": dleft,
                "source": cyc.source,
            })
    rows.sort(key=lambda r: r["days_until"])
    return rows
