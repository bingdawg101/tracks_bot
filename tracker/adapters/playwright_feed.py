"""Generic adapter for JS-only / bot-walled career sites.

Loads the careers page in a headless browser, captures the JSON its front-end fetches,
and maps that into postings. Config:

    adapter: playwright
    source:
      url: https://www.example.com/careers/search
      feed: "*/api/jobs*"          # glob matched against request URLs (JSON responses only)
      items: data.jobs             # dot-path to the list inside the JSON (default: auto-detect)
      map:                         # field -> dot-path within each item
        id: id
        title: title
        location: location.name
        url: absoluteUrl
        department: team
        employment_type: type
      url_prefix: "https://www.example.com/job/"   # prepended when `url` is a bare id/slug

Playwright is an optional dependency: `uv sync --extra browser`.
"""

from __future__ import annotations

import httpx

from ..models import RawPosting, clean_text, stable_id
from .base import Adapter, AdapterError


def _dig(obj: object, path: str):
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list) and part.isdigit():
            cur = cur[int(part)] if int(part) < len(cur) else None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _first_list(obj: object, depth: int = 4):
    """Best-effort: find the largest list of dicts in a nested JSON blob."""
    best: list = []
    stack = [(obj, 0)]
    while stack:
        cur, d = stack.pop()
        if d > depth:
            continue
        if isinstance(cur, list):
            if cur and isinstance(cur[0], dict) and len(cur) > len(best):
                best = cur
            for v in cur[:50]:
                stack.append((v, d + 1))
        elif isinstance(cur, dict):
            for v in cur.values():
                stack.append((v, d + 1))
    return best


class PlaywrightFeedAdapter(Adapter):
    name = "playwright"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        from ..render import RenderUnavailable, capture

        page_url = self._require("url")
        feed_glob = str(self.source.get("feed", "")).strip()
        try:
            cap = await capture(
                page_url,
                url_globs=(feed_glob,) if feed_glob else (),
                wait_selector=self.source.get("wait_selector"),
            )
        except RenderUnavailable as exc:
            raise AdapterError(str(exc)) from exc

        # Pick the JSON response: the one matching the glob, else the biggest job-shaped one.
        payloads = list(cap.json_responses.values())
        if not payloads:
            raise AdapterError(f"{self.firm.slug}: browser captured no JSON from {page_url}")

        items_path = str(self.source.get("items", "")).strip()
        items: list = []
        for body in payloads:
            found = _dig(body, items_path) if items_path else _first_list(body)
            if isinstance(found, list) and found:
                items = found
                break
        if not items:
            raise AdapterError(f"{self.firm.slug}: no job list found in captured JSON")

        fmap = self.source.get("map") or {}
        prefix = str(self.source.get("url_prefix", ""))

        def field(item: dict, key: str) -> str:
            return clean_text(str(_dig(item, fmap.get(key, key)) or ""))

        out: list[RawPosting] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            url = field(it, "url")
            if url and prefix and not url.startswith("http"):
                url = prefix + url
            sid = field(it, "id") or stable_id(field(it, "title"), field(it, "location"))
            out.append(
                RawPosting(
                    source_id=sid,
                    title=field(it, "title"),
                    location=field(it, "location"),
                    url=url or page_url,
                    department=field(it, "department"),
                    employment_type=field(it, "employment_type"),
                    updated_at=field(it, "updated_at"),
                )
            )
        return out
