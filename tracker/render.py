"""Headless-browser helper for JS-only / bot-walled career sites.

Loads a page, lets its scripts run, and captures the JSON responses its front-end
fetches. Playwright is an optional dependency (`uv sync --extra browser`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class RenderUnavailable(RuntimeError):
    """Playwright isn't installed."""


@dataclass
class Capture:
    final_url: str = ""
    html: str = ""
    # url -> parsed JSON body, for every XHR/fetch response that returned JSON
    json_responses: dict[str, object] = field(default_factory=dict)
    request_urls: list[str] = field(default_factory=list)


async def capture(
    url: str,
    *,
    wait_selector: str | None = None,
    url_globs: tuple[str, ...] = (),
    timeout_ms: int = 25_000,
    scroll: bool = True,
) -> Capture:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover
        raise RenderUnavailable(
            "playwright not installed — run: uv sync --extra browser && uv run playwright install chromium"
        ) from exc

    globs = [re.compile(g.replace("*", ".*"), re.IGNORECASE) for g in url_globs]
    cap = Capture()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=_UA, locale="en-GB")
        page = await ctx.new_page()

        async def on_response(resp):
            ct = (resp.headers or {}).get("content-type", "")
            if "json" not in ct.lower():
                return
            if globs and not any(g.search(resp.url) for g in globs):
                return
            try:
                cap.json_responses[resp.url] = json.loads(await resp.text())
            except (ValueError, Exception):
                pass

        page.on("response", on_response)
        page.on("request", lambda r: cap.request_urls.append(r.url))

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=8000)
                except Exception:
                    pass
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            if scroll:
                for _ in range(3):
                    await page.mouse.wheel(0, 4000)
                    await page.wait_for_timeout(700)
            cap.final_url = page.url
            cap.html = await page.content()
        finally:
            await browser.close()

    return cap
