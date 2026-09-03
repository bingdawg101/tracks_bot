"""Telegram Bot API notifier.

Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in the environment (GitHub Actions Secrets).
In --dry-run mode the pipeline prints messages instead of constructing this class.
"""

from __future__ import annotations

import asyncio
import html

import httpx

from ..config import TelegramCreds
from ..models import OpeningEvent

_API = "https://api.telegram.org/bot{token}/sendMessage"
_MAX_LEN = 3800  # Telegram hard limit is 4096; leave headroom.


def _esc(value: str) -> str:
    return html.escape(value or "", quote=False)


def format_events(events: list[OpeningEvent]) -> list[str]:
    """Group events into one message per firm, splitting if a message gets too long."""
    by_firm: dict[str, list[OpeningEvent]] = {}
    for ev in events:
        by_firm.setdefault(ev.firm, []).append(ev)

    messages: list[str] = []
    for firm, evs in by_firm.items():
        header = f"\U0001f6a8 <b>{_esc(firm)}</b> — {len(evs)} role(s) opened"
        blocks = [header]
        for ev in evs:
            loc = f" — {_esc(ev.location)}" if ev.location else ""
            line = f"\n• <b>{_esc(ev.title)}</b>{loc}"
            if ev.url:
                line += f'\n  <a href="{_esc(ev.url)}">Apply</a>'
            if ev.reason:
                line += f"\n  <i>{_esc(ev.reason)}</i>"
            blocks.append(line)
        text = "".join(blocks)
        while len(text) > _MAX_LEN:
            cut = text.rfind("\n•", 0, _MAX_LEN)
            cut = cut if cut > len(header) else _MAX_LEN
            messages.append(text[:cut])
            text = f"{header} (cont.)" + text[cut:]
        messages.append(text)
    return messages


class TelegramNotifier:
    def __init__(self, creds: TelegramCreds) -> None:
        self._creds = creds

    async def send_events(self, events: list[OpeningEvent]) -> None:
        if not events:
            return
        await self._send_all(format_events(events))

    async def send_text(self, text: str) -> None:
        await self._send_all([text])

    async def _send_all(self, messages: list[str]) -> None:
        url = _API.format(token=self._creds.bot_token)
        async with httpx.AsyncClient(timeout=20.0) as client:
            for msg in messages:
                await self._send_one(client, url, msg)
                await asyncio.sleep(0.5)  # stay under ~1 msg/sec per chat

    async def _send_one(self, client: httpx.AsyncClient, url: str, text: str) -> None:
        payload = {
            "chat_id": self._creds.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        for attempt in range(3):
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code == 429:
                    retry_after = int(resp.json().get("parameters", {}).get("retry_after", 2))
                    await asyncio.sleep(retry_after)
                    continue
                resp.raise_for_status()
                return
            except httpx.HTTPError:
                if attempt == 2:
                    raise
                await asyncio.sleep(2 * (attempt + 1))
