"""SAP SuccessFactors "Recruiting Marketing" (RMK) career sites.

Common across commodity / energy firms (Olam, Gunvor, Uniper, SEFE, ...). The site's own
job list is served as an HTML fragment:

    GET https://{host}/tile-search-results/?data={"SearchParameters":{"FirstItem":1,"CountItem":100}}
    -> <li class="job-tile job-id-12345" data-url="/job/Some-Title/12345/"> ...
         <div class="tiletitle">Title  Some Title</div>
         ... Country/Region  GB ... </li>

Configure as:  source: {host: careers.olamagri.com}
Optionally:    source: {host: ..., loc_label: "Location"}   # label preceding the location text
"""

from __future__ import annotations

import json
import re

import httpx
from selectolax.parser import HTMLParser

from ..models import RawPosting, clean_text, stable_id
from .base import Adapter, AdapterError

_PAGE = 100
_MAX_PAGES = 10
_ID_RE = re.compile(r"/(\d{4,})/?$")

# SF often renders the location as a bare ISO country code.
_ISO = {
    "GB": "United Kingdom", "UK": "United Kingdom", "US": "United States", "CH": "Switzerland",
    "SG": "Singapore", "NL": "Netherlands", "DE": "Germany", "FR": "France", "AE": "UAE",
    "HK": "Hong Kong", "IN": "India", "NG": "Nigeria", "AU": "Australia", "CN": "China",
}


def _expand_location(loc: str) -> str:
    key = loc.strip().upper()
    return _ISO.get(key, loc) if len(key) == 2 else loc


class SuccessFactorsAdapter(Adapter):
    name = "successfactors"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        host = self._require("host")
        url = f"https://{host}/tile-search-results/"
        labels = [self.source.get("loc_label", ""), "Country/Region", "Location", "City", "Countries"]
        labels = [x for x in labels if x]

        rows: list[RawPosting] = []
        seen: set[str] = set()
        for page in range(_MAX_PAGES):
            data = json.dumps({"SearchParameters": {
                "FirstItem": page * _PAGE + 1, "CountItem": _PAGE,
                "Sort": [{"Criterion": "PostingStartDate", "Direction": "DESC"}],
            }})
            resp = await client.get(url, params={"data": data}, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            tiles = HTMLParser(resp.text).css("li.job-tile")
            if page == 0 and not tiles:
                raise AdapterError(f"{self.firm.slug}: no SuccessFactors job tiles at {url}")
            new = 0
            for tile in tiles:
                data_url = tile.attributes.get("data-url", "") or ""
                m = _ID_RE.search(data_url.rstrip("/") + "/")
                cls = " ".join(tile.attributes.get("class", "").split())
                cid = m.group(1) if m else ""
                if not cid:
                    cm = re.search(r"job-id-(\w+)", cls)
                    cid = cm.group(1) if cm else stable_id(data_url)
                if cid in seen:
                    continue
                seen.add(cid)
                new += 1

                title_el = tile.css_first(".tiletitle")
                title = clean_text(re.sub(r"^\s*Title\s*", "", title_el.text(separator=" ")) if title_el else "")
                flat = re.sub(r"\s+", " ", tile.text(separator="|", strip=True))
                location = ""
                for lab in labels:
                    lm = re.search(re.escape(lab) + r"\s*\|+\s*([^|]{1,60})", flat)
                    if lm:
                        location = _expand_location(clean_text(lm.group(1)))
                        break
                rows.append(
                    RawPosting(
                        source_id=cid,
                        title=title,
                        location=location,
                        url=f"https://{host}{data_url}" if data_url.startswith("/") else data_url,
                    )
                )
            if new < _PAGE:
                break
        return rows
