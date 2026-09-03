"""Scrape a server-rendered job-list page with CSS selectors.

For firms whose careers page renders the listing into HTML (no JSON feed). Config:

    adapter: html
    source:
      url: https://www.example.com/careers
      render: false            # true => load via headless browser first (JS-rendered)
      rows: 'a[href*="/jobs/"]' # selector for each job row/link
      title: ''                # sub-selector for the title (default: the row's own text)
      location: '.job-location' # sub-selector for location text (optional)
      url_attr: href           # attribute on the row (or `url` sub-selector) holding the link
      location_from_url: '/jobs/[^/]+/([^/]+)/'  # regex group 1 = location, from the link
      url_prefix: https://www.example.com

`render: true` needs the optional browser extra (`uv sync --extra browser`).
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser

from ..models import RawPosting, clean_text, stable_id
from .base import Adapter, AdapterError

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"


class HtmlListAdapter(Adapter):
    name = "html"

    async def _get_html(self, client: httpx.AsyncClient, url: str) -> str:
        if self.source.get("render"):
            from ..render import RenderUnavailable, capture
            try:
                return (await capture(url, wait_selector=self.source.get("wait_selector"))).html
            except RenderUnavailable as exc:
                raise AdapterError(str(exc)) from exc
        resp = await client.get(url, headers={"User-Agent": _UA})
        resp.raise_for_status()
        return resp.text

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        url = self._require("url")
        rows_sel = self._require("rows")
        html = await self._get_html(client, url)
        tree = HTMLParser(html)
        rows = tree.css(rows_sel)
        if not rows:
            raise AdapterError(f"{self.firm.slug}: selector '{rows_sel}' matched nothing")

        title_sel = self.source.get("title")
        loc_sel = self.source.get("location")
        url_attr = self.source.get("url_attr", "href")
        loc_re = self.source.get("location_from_url")
        prefix = self.source.get("url_prefix") or "/".join(url.split("/")[:3])

        out: list[RawPosting] = []
        for row in rows:
            title = clean_text(
                row.css_first(title_sel).text() if title_sel and row.css_first(title_sel)
                else row.text()
            )
            if not title:
                continue
            href = row.attributes.get(url_attr) or ""
            if not href and row.css_first("a"):
                href = row.css_first("a").attributes.get("href", "") or ""
            link = urljoin(prefix + "/", href) if href else url

            location = ""
            if loc_sel and row.css_first(loc_sel):
                location = clean_text(row.css_first(loc_sel).text())
            if not location and loc_re:
                m = re.search(loc_re, href)
                if m:
                    location = clean_text(m.group(1).replace("-", " "))

            out.append(
                RawPosting(
                    source_id=stable_id(href or title),
                    title=title,
                    location=location,
                    url=link,
                )
            )
        return out
