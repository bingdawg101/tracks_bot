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
  repo by the workflow **only when their content changes**, so "no news" runs are silent and the
  git history is a clean audit log of every real opening.
- Live run health is the Actions run history (a badge on the dashboard), not a per-run commit.

## Local usage

```bash
uv venv && uv pip install -e ".[dev]"

uv run python -m tracker list                 # configured firms
uv run python -m tracker check jane-street    # fetch + classify one firm, print only
uv run python -m tracker run --dry-run        # full pipeline, no Telegram
uv run python -m tracker run --seed           # persist baseline, no history/alerts (use after adding firms)
uv run pytest
```

## Deploy (GitHub Actions, free)

The repo must be **public** — `*/5` cron is ~8,640 runs/month, well past the 2,000-minute
private-repo free tier. No secrets live in the code.

### 1. Telegram

1. DM [@BotFather](https://t.me/BotFather) → `/newbot` → copy the bot token.
2. Send your new bot any message (so it has an update to read).
3. `TELEGRAM_BOT_TOKEN=<token> uv run python -m tracker whoami` → copy the `chat_id`.
4. Repo → **Settings → Secrets and variables → Actions → New repository secret**:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

### 2. First run

Push the repo, then repo → **Actions → check → Run workflow**. The committed `state/` is already
the baseline, so the first run should report **0 openings** and send nothing. Send yourself a test
by temporarily disabling a firm's newest role, or just wait for a real one.

### 3. GitHub Pages dashboard

Repo → **Settings → Pages → Source: Deploy from a branch → `main` / `/docs`**. The dashboard lands
at `https://<you>.github.io/<repo>/`.

### 4. Tighter polling (optional but recommended)

GitHub delays scheduled workflows 5–20 min at peak. To fire more reliably:

1. Create a **fine-grained PAT** (Settings → Developer settings → Fine-grained tokens) scoped to
   this repo with **Contents: read and write** (needed for `repository_dispatch`).
2. At [cron-job.org](https://console.cron-job.org) (free), add a job every 2–3 min:
   - URL: `https://api.github.com/repos/<owner>/<repo>/dispatches`
   - Method: `POST`
   - Headers: `Authorization: Bearer <PAT>`, `Accept: application/vnd.github+json`
   - Body: `{"event_type":"poll"}`

## Adding a firm

Add an entry to [`firms.yaml`](firms.yaml). For a Greenhouse board
(`boards.greenhouse.io/<token>`), that's just:

```yaml
  - slug: some-firm
    name: Some Firm
    adapter: greenhouse
    source: {token: somefirm}
```

Per-firm `filters:` lists are merged with `defaults:`. Use `check` to tune them before enabling,
then `run --seed` once so the new firm's current roles don't all fire as alerts.

## Status

- **Phase 1 ✓** — core pipeline, Greenhouse + Lever adapters, structured-signal classifier, CLI.
- **Phase 2 ✓** — GitHub Actions (`check.yml` + `ci.yml`), commit-back, dashboard generator.
- **Phase 3** — dashboard polish.
- **Phase 4** — Workday / Ashby / SmartRecruiters / generic-HTML adapters (Citadel, DRW, Optiver, banks).
- **Phase 5** — full firm list + per-firm filter tuning + weekly digest.

10 firms live on Greenhouse: Jane Street, Hudson River Trading, Five Rings, Squarepoint, Aquatic,
IMC, Jump Trading, Tower Research, Flow Traders, Virtu.
