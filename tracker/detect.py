"""Identify which ATS backs a careers page, and emit a firms.yaml stub.

Used to onboard firms in bulk: `python -m tracker detect <careers-url> --name "Firm"`.
Fetches the page (and, if it looks like a landing page, one likely job-listing sub-page),
then matches known ATS URL signatures against links, script srcs and inline text.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

import httpx

from .models import clean_text

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"

# name -> (compiled regex, function(match) -> source dict)
_SIGNATURES: list[tuple[str, re.Pattern, object]] = [
    ("greenhouse", re.compile(r"(?:job-)?boards(?:-api)?\.greenhouse\.io/(?:v1/boards/)?embed/job_board\?for=([a-z0-9_-]+)", re.IGNORECASE),
     lambda m: {"token": m.group(1)}),
    ("greenhouse", re.compile(r"(?:job-)?boards(?:-api)?\.greenhouse\.io/(?:v1/boards/)?([a-z0-9_-]+)", re.IGNORECASE),
     lambda m: {"token": m.group(1)}),
    ("lever", re.compile(r"(?:jobs|api)\.lever\.co/(?:v0/postings/)?([a-z0-9_-]+)", re.IGNORECASE),
     lambda m: {"token": m.group(1)}),
    ("ashby", re.compile(r"(?:jobs\.ashbyhq\.com|api\.ashbyhq\.com/posting-api/job-board)/([a-z0-9_-]+)", re.IGNORECASE),
     lambda m: {"token": m.group(1)}),
    ("smartrecruiters", re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/(?:v1/companies/)?([A-Za-z0-9_-]+)", re.IGNORECASE),
     lambda m: {"company": m.group(1)}),
    ("smartrecruiters", re.compile(r"api\.smartrecruiters\.com/v1/companies/([A-Za-z0-9_-]+)", re.IGNORECASE),
     lambda m: {"company": m.group(1)}),
    ("workday", re.compile(r"([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:wday/cxs/[a-z0-9-]+/)?([A-Za-z0-9_-]+)", re.IGNORECASE),
     lambda m: {"tenant": m.group(1), "wd": m.group(2), "site": m.group(3)}),
    ("oracle_orc", re.compile(r"(https?://)?([a-z0-9.-]+oraclecloud\.com)/hcmUI/CandidateExperience/[a-z-]+/sites/([A-Za-z0-9_]+)", re.IGNORECASE),
     lambda m: {"host": m.group(2), "site": m.group(3)}),
    ("workable", re.compile(r"(?:apply\.workable\.com|([a-z0-9-]+)\.workable\.com)/(?:api/v\d/accounts/)?([a-z0-9-]+)?", re.IGNORECASE),
     lambda m: {"token": m.group(2) or m.group(1)}),
    ("teamtailor", re.compile(r"([a-z0-9-]+)\.teamtailor\.com", re.IGNORECASE),
     lambda m: {"token": m.group(1)}),
    ("recruitee", re.compile(r"([a-z0-9-]+)\.recruitee\.com", re.IGNORECASE),
     lambda m: {"token": m.group(1)}),
    ("personio", re.compile(r"([a-z0-9-]+)\.jobs\.personio\.(?:de|com)", re.IGNORECASE),
     lambda m: {"token": m.group(1)}),
    ("bamboohr", re.compile(r"([a-z0-9-]+)\.bamboohr\.com/(?:careers|jobs)", re.IGNORECASE),
     lambda m: {"token": m.group(1)}),
    ("beesite", re.compile(r"(api-[a-z0-9-]+\.beesite\.de)", re.IGNORECASE),
     lambda m: {"host": m.group(1)}),
]

# ATS we recognise but don't have an adapter for yet — report so we know what's needed.
_UNSUPPORTED = {
    "eightfold": re.compile(r"\.eightfold\.ai", re.IGNORECASE),
    "phenom": re.compile(r"phenompeople|phenom\.com|/phapp/", re.IGNORECASE),
    "avature": re.compile(r"\.avature\.net", re.IGNORECASE),
    "oleeo/tal.net": re.compile(r"\.tal\.net", re.IGNORECASE),
    "successfactors": re.compile(r"\.successfactors\.(?:eu|com)|/careersection/", re.IGNORECASE),
    "icims": re.compile(r"\.icims\.com", re.IGNORECASE),
    "taleo": re.compile(r"\.taleo\.net", re.IGNORECASE),
    "radancy/talentbrew": re.compile(r"talentbrew|radancy|search-jobs/results", re.IGNORECASE),
    "jobvite": re.compile(r"\.jobvite\.com", re.IGNORECASE),
    "successfactors-rmk": re.compile(r"/careers/careersection/", re.IGNORECASE),
}

_SUBPAGE_HINTS = re.compile(r"(job|career|vacan|opportun|opening|position|search|role)", re.IGNORECASE)


@dataclass
class Detection:
    adapter: str | None
    source: dict
    confidence: str
    note: str = ""


async def _fetch(client: httpx.AsyncClient, url: str) -> str:
    try:
        r = await client.get(url)
        return r.text if r.status_code < 400 else ""
    except httpx.HTTPError:
        return ""


_GH_APPLY = re.compile(r"gh_jid=|gh_src=|grnh\.se/", re.IGNORECASE)
_GH_TOKEN_FROM_APPLY = re.compile(r"greenhouse\.io/(?:embed/job_app\?for=|)([a-z0-9_-]+)", re.IGNORECASE)


def _scan(text: str) -> Detection | None:
    for adapter, pattern, builder in _SIGNATURES:
        m = pattern.search(text)
        if m:
            src = builder(m)
            if all(src.values()):
                return Detection(adapter, src, "high", "matched ATS URL")
    for label, pattern in _UNSUPPORTED.items():
        if pattern.search(text):
            return Detection(None, {}, "n/a", f"uses {label} — no adapter yet")
    if _GH_APPLY.search(text):
        m = _GH_TOKEN_FROM_APPLY.search(text)
        return Detection(
            "greenhouse", {"token": m.group(1) if m else "?"},
            "medium" if m else "low",
            "Greenhouse apply links present — confirm the board token",
        )
    return None


def _candidate_subpages(html: str, base: str) -> list[str]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
    out: list[str] = []
    for h in hrefs:
        if not _SUBPAGE_HINTS.search(h):
            continue
        if h.startswith("http"):
            out.append(h)
        elif h.startswith("/"):
            out.append(base.rstrip("/") + h)
    # de-dupe, keep first few
    seen: dict[str, None] = {}
    for u in out:
        seen.setdefault(u.split("#")[0], None)
    return list(seen)[:6]


_FILLER = {"the", "and", "group", "holdings", "international", "global", "co", "inc", "ltd",
           "llc", "plc", "sa", "ag", "as", "limited", "company", "corp", "corporation"}


def _candidate_tokens(name: str, url: str) -> list[str]:
    host = url.split("/")[2].replace("www.", "").split(".")[0] if "://" in url else ""
    words = re.findall(r"[a-z0-9]+", name.lower())
    core = [w for w in words if w not in _FILLER] or words
    cands = [
        "".join(words), "-".join(words),
        "".join(core), "-".join(core),
        core[0] if core else "",
        (core[0] + core[1]) if len(core) > 1 else "",
        host,
    ]
    # common commodity-firm suffixes bolted onto the first word
    for suf in ("group", "trading", "commodities", "energy", "partners", "capital"):
        if core:
            cands.append(core[0] + suf)
            cands.append(f"{core[0]}-{suf}")
    seen: dict[str, None] = {}
    for c in cands:
        if c and len(c) > 2:
            seen.setdefault(c, None)
    return list(seen)


async def _probe_apis(client: httpx.AsyncClient, tokens: list[str]) -> Detection | None:
    """Directly hit the public ATS APIs for each candidate token."""
    checks = [
        ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{t}/jobs",
         lambda j: isinstance(j, dict) and j.get("jobs"), lambda t: {"token": t}),
        ("lever", "https://api.lever.co/v0/postings/{t}?mode=json&limit=1",
         lambda j: isinstance(j, list), lambda t: {"token": t}),
        ("ashby", "https://api.ashbyhq.com/posting-api/job-board/{t}",
         lambda j: isinstance(j, dict) and j.get("jobs"), lambda t: {"token": t}),
        ("smartrecruiters", "https://api.smartrecruiters.com/v1/companies/{t}/postings?limit=1",
         lambda j: isinstance(j, dict) and j.get("totalFound", 0) > 0, lambda t: {"company": t}),
        ("recruitee", "https://{t}.recruitee.com/api/offers/",
         lambda j: isinstance(j, dict) and j.get("offers"), lambda t: {"token": t}),
        ("teamtailor", "https://{t}.teamtailor.com/jobs.json",
         lambda j: isinstance(j, dict) and j.get("items"), lambda t: {"token": t}),
        ("workable", "https://apply.workable.com/api/v1/widget/accounts/{t}?details=true",
         lambda j: isinstance(j, dict) and j.get("jobs"), lambda t: {"token": t}),
        ("personio", "https://{t}.jobs.personio.com/search.json",
         lambda j: isinstance(j, list) and j, lambda t: {"token": t}),
        ("personio", "https://{t}.jobs.personio.de/search.json",
         lambda j: isinstance(j, list) and j, lambda t: {"token": t}),
    ]
    async def try_one(ats, tmpl, ok, build, tok):
        try:
            r = await client.get(tmpl.format(t=tok))
            if r.status_code == 200 and ok(r.json()):
                return Detection(ats, build(tok), "high", f"public {ats} API responds for '{tok}'")
        except (httpx.HTTPError, ValueError):
            pass
        return None

    tasks = [try_one(*c, tok) for c in checks for tok in tokens]
    for coro in asyncio.as_completed(tasks):
        hit = await coro
        if hit:
            return hit
    return None


async def detect(url: str, name: str = "", *, render: bool = False) -> Detection:
    origin = "/".join(url.split("/")[:3])
    hit = _scan(url)
    if hit:
        return hit
    async with httpx.AsyncClient(
        timeout=15, follow_redirects=True, headers={"User-Agent": _UA}
    ) as client:
        html = await _fetch(client, url)
        hit = _scan(html)
        if hit:
            return hit
        for sub in _candidate_subpages(html, origin):
            hit = _scan(await _fetch(client, sub))
            if hit:
                hit.note += f" (via {sub})"
                return hit
        probe = await _probe_apis(client, _candidate_tokens(name or origin, url))
        if probe:
            return probe

    if render:
        return await _detect_rendered(url)
    return Detection(None, {}, "none", "no static signature — retry with --render for a browser check")


async def _detect_rendered(url: str) -> Detection:
    from .render import RenderUnavailable, capture

    try:
        cap = await capture(url)
    except RenderUnavailable as exc:
        return Detection(None, {}, "none", str(exc))

    haystack = "\n".join([cap.final_url, *cap.request_urls, *cap.json_responses])
    hit = _scan(haystack)
    if hit:
        hit.note += " (browser-rendered)"
        return hit

    # A page that fetched its own JSON job feed — usable via a custom/playwright adapter.
    for feed_url, body in cap.json_responses.items():
        blob = json.dumps(body)[:20000].lower()
        if any(k in blob for k in ('"job', '"position', '"vacanc', '"requisition', '"posting')):
            return Detection(
                None, {"feed": feed_url}, "medium",
                f"custom JSON feed at {feed_url} — needs a bespoke or playwright adapter",
            )
    return Detection(None, {}, "none", "rendered, but no recognisable job feed found")


def yaml_stub(slug: str, name: str, d: Detection) -> str:
    if not d.adapter:
        return f"  # {slug} ({name}): {d.note}"
    src = ", ".join(f"{k}: {v}" for k, v in d.source.items())
    return (
        f"  - slug: {slug}\n"
        f"    name: {clean_text(name)}\n"
        f"    adapter: {d.adapter}\n"
        f"    source: {{{src}}}   # detected {d.confidence} — {d.note}"
    )
