"""Load firms.yaml and runtime settings."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMS_FILE = REPO_ROOT / "firms.yaml"
STATE_DIR = REPO_ROOT / "state"
RAW_DIR = STATE_DIR / "raw"
HISTORY_FILE = REPO_ROOT / "history.json"
DOCS_DIR = REPO_ROOT / "docs"


class FilterConfig(BaseModel):
    """Per-firm or global filter rules. Firm-level lists are merged with the defaults."""

    # A posting's title/department must contain at least one of these (word-boundary, case-insensitive).
    include: list[str] = Field(default_factory=list)
    # ... and none of these (word-boundary, matched against title + department).
    exclude: list[str] = Field(default_factory=list)
    # Location must contain one of these (substring). Empty => any location passes.
    locations: list[str] = Field(default_factory=list)
    # ...but is rejected if it also contains one of these (kills "London, Ontario" etc).
    location_excludes: list[str] = Field(default_factory=list)
    # Optional: department/team must contain one of these (substring). Empty => any.
    departments: list[str] = Field(default_factory=list)
    # Terms that signal graduate / final-year / internship eligibility (word-boundary,
    # matched against title, then description as a weaker signal).
    eligibility_terms: list[str] = Field(default_factory=list)
    # Structured employment-type values (substring) that mean "eligible" — the authoritative
    # signal when the source provides an employment type.
    eligible_employment_types: list[str] = Field(default_factory=list)
    # Structured employment-type values (substring) that definitively mean "not eligible".
    excluded_employment_types: list[str] = Field(default_factory=list)
    # If True, a posting that fits location + eligibility but not `include` is REVIEW, not IGNORE.
    review_ambiguous: bool = True


class FirmConfig(BaseModel):
    slug: str
    name: str
    adapter: str                     # greenhouse | lever | ashby | smartrecruiters | workday | html
    # Adapter-specific connection settings, e.g. {"token": "janestreet"}.
    source: dict = Field(default_factory=dict)
    enabled: bool = True
    filters: FilterConfig = Field(default_factory=FilterConfig)
    notes: str = ""


class Settings(BaseModel):
    defaults: FilterConfig = Field(default_factory=FilterConfig)
    firms: list[FirmConfig] = Field(default_factory=list)
    # Consecutive failures before an adapter-health alert / non-zero exit.
    failure_alert_threshold: int = 3
    http_timeout_seconds: float = 20.0
    http_retries: int = 2
    max_concurrency: int = 8

    def enabled_firms(self) -> list[FirmConfig]:
        return [f for f in self.firms if f.enabled]

    def firm(self, slug: str) -> FirmConfig | None:
        return next((f for f in self.firms if f.slug == slug), None)

    def merged_filter(self, firm: FirmConfig) -> FilterConfig:
        """Firm filter lists extend the defaults; scalars fall back to firm then default."""
        d = self.defaults
        f = firm.filters
        return FilterConfig(
            include=_dedupe(d.include + f.include),
            exclude=_dedupe(d.exclude + f.exclude),
            locations=_dedupe(d.locations + f.locations),
            location_excludes=_dedupe(d.location_excludes + f.location_excludes),
            departments=_dedupe(d.departments + f.departments),
            eligibility_terms=_dedupe(d.eligibility_terms + f.eligibility_terms),
            eligible_employment_types=_dedupe(
                d.eligible_employment_types + f.eligible_employment_types
            ),
            excluded_employment_types=_dedupe(
                d.excluded_employment_types + f.excluded_employment_types
            ),
            review_ambiguous=f.review_ambiguous,
        )


def _dedupe(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for it in items:
        seen.setdefault(it.strip(), None)
    return [k for k in seen if k]


def load_settings(path: Path | None = None) -> Settings:
    path = path or FIRMS_FILE
    data = yaml.safe_load(path.read_text()) or {}
    return Settings.model_validate(data)


class TelegramCreds(BaseModel):
    bot_token: str
    chat_id: str


def telegram_creds() -> TelegramCreds | None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat_id:
        return TelegramCreds(bot_token=token, chat_id=chat_id)
    return None
