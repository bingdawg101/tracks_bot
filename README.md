# Careers Tracker

Accurate, fast alerts when trading firms open **graduate / final-year-eligible internship** roles
in commodities trading, quant research, quant trading, sales & trading and global markets.

Scrapes each firm's careers source directly (Greenhouse / Lever JSON APIs, more to come), runs on
GitHub Actions every few minutes, and pushes a Telegram alert the moment a matching role appears.

## How it works

```
fetch (per-firm adapter) -> normalise -> classify (filters.py) -> diff vs state/ -> Telegram + history + dashboard
```

- **No false "it closed"**: a failed scrape never mutates the tracked set; closure is only inferred
  from a *successful* fetch that drops a previously-seen posting.
- **Nothing silently dropped**: postings that fit location + eligibility but not the role keywords
  become `REVIEW` (soft alert + dashboard), not `IGNORE`.
- State (`state/`), history (`history.json`) and the dashboard (`docs/`) are committed back to the
  repo by the workflow, so the whole system is auditable from git history.

## Local usage

```bash
uv venv && uv pip install -e ".[dev]"

uv run python -m tracker list                 # configured firms
uv run python -m tracker check jane-street    # fetch + classify one firm, print only
uv run python -m tracker run --dry-run        # full pipeline, no Telegram, no writes if --no-persist
uv run pytest
```

## Telegram setup

1. DM [@BotFather](https://t.me/BotFather) → `/newbot` → copy the bot token.
2. Send your new bot any message.
3. `TELEGRAM_BOT_TOKEN=<token> uv run python -m tracker whoami` → copy the `chat_id`.
4. Add both as GitHub Actions repo secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

## Adding a firm

Add an entry to [`firms.yaml`](firms.yaml). For a Greenhouse board
(`boards.greenhouse.io/<token>`), that's just:

```yaml
  - slug: some-firm
    name: Some Firm
    adapter: greenhouse
    source: {token: somefirm}
```

Per-firm `filters:` lists are merged with `defaults:`. Use `check` to tune them before enabling.

## Status

**Phase 1** — core pipeline, Greenhouse + Lever adapters, dry-run CLI. See
[the plan](../.claude/plans/) for the roadmap (Actions workflow, dashboard, more adapters).
