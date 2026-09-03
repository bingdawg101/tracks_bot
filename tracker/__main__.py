"""CLI entry point.

    python -m tracker run [--dry-run] [--only slug,slug] [--no-persist]
    python -m tracker check <slug>          # fetch + classify one firm, print, never notify/persist
    python -m tracker list                  # show configured firms
    python -m tracker whoami                # print Telegram chat id for the configured bot token
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

import httpx

from . import dashboard
from .config import load_settings, telegram_creds
from .detect import detect, yaml_stub
from .notify import TelegramNotifier
from .pipeline import run


def _cmd_list(args: argparse.Namespace) -> int:
    settings = load_settings()
    for f in settings.firms:
        flag = "on " if f.enabled else "off"
        print(f"[{flag}] {f.slug:24s} {f.adapter:10s} {f.name}")
    print(f"\n{len(settings.enabled_firms())}/{len(settings.firms)} enabled")
    return 0


async def _run_check(slug: str) -> int:
    settings = load_settings()
    firm = settings.firm(slug)
    if not firm:
        print(f"no firm with slug '{slug}'", file=sys.stderr)
        return 2
    result = await run(settings, only=[slug], persist=False, dry_run=True)
    fr = result.results[0]
    if not fr.ok:
        print(f"FETCH FAILED: {fr.error}", file=sys.stderr)
        return 1
    print(f"\n=== {fr.name} ({slug}) ===")
    print(f"MATCH ({len(fr.matched)}):")
    for p in sorted(fr.matched, key=lambda x: -x.comp_k):
        et = f" [{p.employment_type}]" if p.employment_type else ""
        money = f"~£{p.comp_k}k  " if p.comp_k else ""
        print(f"  + {money}{p.summary_line()}{et}\n      {p.match_reason}\n      {p.url}")
    print(f"\nREVIEW ({len(fr.review)}):")
    for p in sorted(fr.review, key=lambda x: -x.comp_k):
        et = f" [{p.employment_type}]" if p.employment_type else ""
        money = f"~£{p.comp_k}k  " if p.comp_k else ""
        print(f"  ? {money}{p.summary_line()}{et}\n      {p.match_reason}")
    if fr.events:
        print(f"\nWould alert on {len(fr.events)} opening(s) (none sent — check mode).")
    return 0


async def _run_pipeline(args: argparse.Namespace) -> int:
    settings = load_settings()
    only = args.only.split(",") if args.only else None

    notifier = None
    if not args.dry_run:
        creds = telegram_creds()
        if creds:
            notifier = TelegramNotifier(creds)
        else:
            print("WARN: no Telegram creds in env; running as dry-run", file=sys.stderr)

    result = await run(
        settings,
        only=only,
        persist=not args.no_persist,
        dry_run=args.dry_run,
        seed=args.seed,
        notifier=notifier,
    )

    for fr in result.results:
        status = "ok" if fr.ok else f"FAIL x{fr.failure_count}"
        extra = f"{len(fr.matched)} match / {len(fr.review)} review"
        if not fr.ok:
            extra = fr.error
        print(f"{fr.slug:24s} {status:10s} {extra}")

    events = result.events
    print(f"\n{len(events)} opening(s) detected.")
    for ev in events:
        print(f"  \U0001f6a8 {ev.firm}: {ev.title} — {ev.location}")
        if args.dry_run and ev.url:
            print(f"     {ev.url}")

    if not args.no_persist:
        dashboard.render(settings, repo=os.environ.get("GITHUB_REPOSITORY"))
        print("dashboard: docs/index.html")

    threshold = settings.failure_alert_threshold
    # Rate-limits / timeouts are transient — log but don't cry wolf; only real breakage
    # (404 / 500 / parse errors) counts toward the health alert.
    transient = re.compile(r"429|rate.?limit|timed out|timeout|temporarily|503", re.IGNORECASE)
    hard_fail = [
        r for r in result.unhealthy
        if r.failure_count >= threshold and not transient.search(r.error)
    ]
    if hard_fail:
        names = ", ".join(f"{r.slug} (x{r.failure_count})" for r in hard_fail)
        print(f"\nADAPTER HEALTH: {names} — needs attention", file=sys.stderr)
        if notifier:
            await notifier.send_text(
                "⚠️ careers-tracker: adapter(s) failing repeatedly: " + names
            )
        return 1
    return 0


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "firm"


def _parse_detect_file(path: str) -> list[tuple[str, str, str]]:
    """Lines of 'Name, url' or 'slug | Name | url' → (slug, name, url) triples."""
    jobs: list[tuple[str, str, str]] = []
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in re.split(r"\s*[|,]\s*", line, maxsplit=2)]
        if len(parts) == 3:
            jobs.append((parts[0], parts[1], parts[2]))
        elif len(parts) == 2:
            jobs.append((_slugify(parts[0]), parts[0], parts[1]))
        else:
            jobs.append((_slugify(parts[0]), parts[0], parts[0]))
    return jobs


async def _run_detect(args: argparse.Namespace) -> int:
    if args.file:
        jobs = _parse_detect_file(args.file)
    else:
        name = args.name or args.url.split("/")[2].replace("www.", "")
        jobs = [(args.slug or _slugify(name), name, args.url)]

    sem = asyncio.Semaphore(2 if args.render else 6)

    async def one(slug, name, url):
        async with sem:
            d = await detect(url, name, render=args.render)
        return yaml_stub(slug, name, d)

    stubs = await asyncio.gather(*(one(s, n, u) for s, n, u in jobs))
    print("\n".join(stubs))
    return 0


async def _run_whoami() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("set TELEGRAM_BOT_TOKEN first", file=sys.stderr)
        return 2
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    async with httpx.AsyncClient(timeout=20.0) as client:
        data = (await client.get(url)).json()
    if not data.get("ok"):
        print(f"Telegram error: {data}", file=sys.stderr)
        return 1
    seen = []
    for upd in data.get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat", {})
        if chat:
            seen.append(f"  chat_id={chat.get('id')}  ({chat.get('type')} {chat.get('title') or chat.get('username') or chat.get('first_name')})")
    if seen:
        print("Send your bot a message first, then:")
        print("\n".join(dict.fromkeys(seen)))
    else:
        print("No updates. Send your bot a DM (or add it to your channel) and retry.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tracker")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="run the full pipeline")
    p_run.add_argument("--dry-run", action="store_true", help="never send Telegram messages")
    p_run.add_argument("--no-persist", action="store_true", help="do not write state/history")
    p_run.add_argument("--seed", action="store_true",
                       help="establish baseline: persist state but log no history / send no alerts")
    p_run.add_argument("--only", help="comma-separated firm slugs")

    p_check = sub.add_parser("check", help="fetch + classify one firm, print only")
    p_check.add_argument("slug")

    sub.add_parser("list", help="list configured firms")
    sub.add_parser("whoami", help="discover Telegram chat id")
    sub.add_parser("dashboard", help="regenerate docs/ from current state")

    p_det = sub.add_parser("detect", help="identify a firm's ATS and print a firms.yaml stub")
    p_det.add_argument("url", nargs="?", help="careers page URL")
    p_det.add_argument("--name", help="firm display name")
    p_det.add_argument("--slug", help="firm slug")
    p_det.add_argument("--file", help="batch: file of 'Name, url' or 'slug | Name | url' lines")
    p_det.add_argument("--render", action="store_true",
                       help="fall back to a headless browser (needs: uv sync --extra browser)")

    args = parser.parse_args(argv)

    if args.cmd == "list":
        return _cmd_list(args)
    if args.cmd == "dashboard":
        dashboard.render(load_settings(), repo=os.environ.get("GITHUB_REPOSITORY"))
        print("wrote docs/index.html")
        return 0
    if args.cmd == "check":
        return asyncio.run(_run_check(args.slug))
    if args.cmd == "detect":
        if not args.url and not args.file:
            print("give a URL or --file", file=sys.stderr)
            return 2
        return asyncio.run(_run_detect(args))
    if args.cmd == "whoami":
        return asyncio.run(_run_whoami())
    if args.cmd == "run":
        return asyncio.run(_run_pipeline(args))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
