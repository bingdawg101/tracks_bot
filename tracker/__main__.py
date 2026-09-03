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
import sys

import httpx

from .config import load_settings, telegram_creds
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
    for p in fr.matched:
        et = f" [{p.employment_type}]" if p.employment_type else ""
        print(f"  + {p.summary_line()}{et}\n      {p.match_reason}\n      {p.url}")
    print(f"\nREVIEW ({len(fr.review)}):")
    for p in fr.review:
        et = f" [{p.employment_type}]" if p.employment_type else ""
        print(f"  ? {p.summary_line()}{et}\n      {p.match_reason}")
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

    threshold = settings.failure_alert_threshold
    hard_fail = [r for r in result.unhealthy if r.failure_count >= threshold]
    if hard_fail:
        names = ", ".join(f"{r.slug} (x{r.failure_count})" for r in hard_fail)
        print(f"\nADAPTER HEALTH: {names} — needs attention", file=sys.stderr)
        if notifier:
            await notifier.send_text(
                "⚠️ careers-tracker: adapter(s) failing repeatedly: " + names
            )
        return 1
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
    p_run.add_argument("--only", help="comma-separated firm slugs")

    p_check = sub.add_parser("check", help="fetch + classify one firm, print only")
    p_check.add_argument("slug")

    sub.add_parser("list", help="list configured firms")
    sub.add_parser("whoami", help="discover Telegram chat id")

    args = parser.parse_args(argv)

    if args.cmd == "list":
        return _cmd_list(args)
    if args.cmd == "check":
        return asyncio.run(_run_check(args.slug))
    if args.cmd == "whoami":
        return asyncio.run(_run_whoami())
    if args.cmd == "run":
        return asyncio.run(_run_pipeline(args))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
