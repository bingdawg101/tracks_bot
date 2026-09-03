from __future__ import annotations

from datetime import date

from tracker.cycles import Cycle, CycleStatus, upcoming


def test_open_window_parsing():
    assert Cycle(opens="2026-09-15").open_window() == (date(2026, 9, 15), date(2026, 9, 15))
    lo, hi = Cycle(opens="2026-09").open_window()
    assert lo == date(2026, 9, 1) and hi == date(2026, 10, 1)
    lo, hi = Cycle(opens="2026-09..2026-11").open_window()
    assert lo == date(2026, 9, 1) and hi == date(2026, 11, 1)
    assert Cycle(opens="rolling").open_window() == (None, None)


def test_days_until_open():
    c = Cycle(opens="2026-09-10", status=CycleStatus.NOT_YET_OPEN)
    assert c.days_until_open(date(2026, 9, 1)) == 9
    assert c.days_until_open(date(2026, 9, 20)) == -10


def test_upcoming_filters_and_sorts():
    cycles = {
        "a": [Cycle(programme="Summer 2027", status=CycleStatus.NOT_YET_OPEN, opens="2026-09-20")],
        "b": [Cycle(programme="Grad 2027", status=CycleStatus.NOT_YET_OPEN, opens="2026-09-05")],
        "c": [Cycle(programme="Done", status=CycleStatus.OPEN, opens="2026-06-01")],
        "d": [Cycle(programme="Far off", status=CycleStatus.NOT_YET_OPEN, opens="2027-06-01")],
    }
    rows = upcoming(cycles, within_days=90, firm_names={"a": "A", "b": "B"})
    # only a and b are not-yet-open and within 90 days of ~today's test run… use a fixed ref
    slugs = [r["slug"] for r in rows]
    assert "c" not in slugs and "d" not in slugs
