"""Render the static status dashboard (docs/index.html + docs/data.json).

Reordered around the thing that matters: what is about to open, and what has *just*
opened. Roles that were already open when we first saw them are collapsed into a muted
"probably too late" section and never alert.
"""

from __future__ import annotations

import json

from jinja2 import Template

from .config import DOCS_DIR, HISTORY_FILE, Settings
from .cycles import CycleStatus, upcoming
from .diff import load_state
from .models import MatchLevel, utcnow

DEFAULT_REPO = "bingdawg101/tracks_bot"

_TEMPLATE = Template(
    """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Careers Tracker</title>
<style>
  :root { color-scheme: light dark; --bg:#fff; --fg:#111; --muted:#666; --line:#e3e3e3;
    --match:#0a7d32; --review:#8a6d00; --fail:#b00020; --soon:#1d4ed8; --card:#fafafa; }
  @media (prefers-color-scheme: dark) { :root { --bg:#14151a; --fg:#e8e8e8; --muted:#9aa0a6;
    --line:#2a2c33; --match:#4ccf6f; --review:#e0b53d; --fail:#ff6b81; --soon:#7aa2ff; --card:#1c1d23; } }
  * { box-sizing: border-box; }
  body { margin:0; font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    background:var(--bg); color:var(--fg); padding:24px; max-width:1040px; margin:0 auto; }
  h1 { font-size:20px; margin:0 0 4px; } h2 { font-size:15px; margin:30px 0 10px; }
  .meta { color:var(--muted); font-size:13px; margin-bottom:12px; }
  a { color:inherit; } table { border-collapse:collapse; width:100%; font-size:13.5px; }
  th,td { text-align:left; padding:7px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
  th { color:var(--muted); font-weight:600; }
  .n { font-variant-numeric:tabular-nums; white-space:nowrap; }
  .ok{color:var(--match)} .warn{color:var(--review)} .bad{color:var(--fail)} .soon{color:var(--soon)}
  ul.roles { margin:4px 0 0; padding-left:18px; } ul.roles li { margin:3px 0; }
  .tag { color:var(--muted); font-size:12px; }
  .hist li { margin:3px 0; } code { background:var(--card); padding:1px 4px; border-radius:4px; }
  details { margin-top:6px; } summary { cursor:pointer; color:var(--muted); font-size:13px; }
  .big { font-size:15px; }
  .cal td:first-child { font-weight:600; }
</style></head><body>
<h1>Careers Tracker</h1>
<div class="meta">
  Graduate / final-year / internship roles &mdash; commodities, quant, S&amp;T, global markets &mdash; London/UK.
  {{ enabled_count }} firms watched.<br>
  <img alt="last check" src="https://img.shields.io/github/actions/workflow/status/{{ repo }}/check.yml?label=last%20check&cacheSeconds=300">
  &middot; <a href="https://github.com/{{ repo }}/actions/workflows/check.yml">run history</a>
  {% if last_opening %}&middot; last opening detected {{ last_opening[:16] }} UTC{% endif %}
</div>

<h2 class="big">&#128309; Opening soon &mdash; get ready ({{ soon|length }})</h2>
{% if soon %}
<table class="cal">
<tr><th>When</th><th>Expected</th><th>Firm</th><th>Programme</th><th>Basis</th></tr>
{% for c in soon %}
<tr>
  <td class="soon n">{{ c.when }}</td>
  <td class="n tag">{{ c.opens_display }}{% if c.estimate %} <span title="estimate">~</span>{% endif %}</td>
  <td>{{ c.firm }}</td>
  <td>{{ c.programme }}</td>
  <td class="tag">{{ c.source }}</td>
</tr>
{% endfor %}
</table>
{% else %}<div class="tag">No cycles flagged as opening in the next ~4 months. Add expected dates under <code>cycles:</code> in firms.yaml.</div>{% endif %}

<h2 class="big">&#127381; Just opened &mdash; apply now ({{ fresh|length }})</h2>
{% if fresh %}
<table>
<tr><th class="n">Age</th><th class="n">Est. pay</th><th>Firm</th><th>Role</th></tr>
{% for r in fresh %}
<tr>
  <td class="n ok">{{ r.age_days }}d ago</td>
  <td class="n">{% if r.comp_k %}<b>&pound;{{ r.comp_k }}k</b>{% endif %}</td>
  <td>{{ r.firm }}</td>
  <td>{% if r.url %}<a href="{{ r.url }}">{{ r.title }}</a>{% else %}{{ r.title }}{% endif %}
      <span class="tag">&mdash; {{ r.location }}{% if r.employment_type %} &middot; {{ r.employment_type }}{% endif %}</span></td>
</tr>
{% endfor %}
</table>
{% else %}<div class="tag">Nothing new in the last {{ fresh_days }} days.</div>{% endif %}

<h2>Recent openings (history)</h2>
{% if history %}
<ul class="hist">
{% for h in history %}
  <li><code>{{ h.detected_at[:16] }}</code> &mdash;
    {% if h.comp_k %}<b>&pound;{{ h.comp_k }}k</b> &middot; {% endif %}<b>{{ h.firm }}</b>:
    {% if h.url %}<a href="{{ h.url }}">{{ h.title }}</a>{% else %}{{ h.title }}{% endif %}
    <span class="tag">{{ h.location }}</span></li>
{% endfor %}
</ul>
{% else %}<div class="tag">Nothing detected yet &mdash; baselines established, watching for changes.</div>{% endif %}

<details>
<summary>Already open &mdash; likely too late ({{ stale|length }} roles across {{ stale_firms }} firms)</summary>
<table>
<tr><th class="n">Age</th><th class="n">Est. pay</th><th>Firm</th><th>Role</th></tr>
{% for r in stale %}
<tr>
  <td class="n tag">{{ r.age_days }}d</td>
  <td class="n">{% if r.comp_k %}&pound;{{ r.comp_k }}k{% endif %}</td>
  <td>{{ r.firm }}</td>
  <td>{% if r.url %}<a href="{{ r.url }}">{{ r.title }}</a>{% else %}{{ r.title }}{% endif %}
      <span class="tag">&mdash; {{ r.location }}</span></td>
</tr>
{% endfor %}
</table>
</details>

<details>
<summary>Firm coverage &amp; health ({{ firms|length }})</summary>
<table>
<tr><th>Firm</th><th>Cycle</th><th class="n">Match</th><th class="n">Review</th><th>Health</th></tr>
{% for f in firms %}
<tr>
  <td>{{ f.name }}{% if f.tier %} <span class="tag">{{ f.tier.replace('_',' ') }}</span>{% endif %}</td>
  <td class="tag">{{ f.cycle_note }}</td>
  <td class="n">{{ f.match_count }}</td>
  <td class="n">{{ f.review_count }}</td>
  <td>{% if f.failure_count %}<span class="bad">failing &times;{{ f.failure_count }}</span>
      {% else %}<span class="ok">ok</span>{% endif %}</td>
</tr>
{% endfor %}
</table>
</details>

<p class="tag">Pay figures are rough first-year total-comp estimates (London) by firm tier &times; role
family &mdash; for ranking, not gospel. "Opening soon" dates are expected windows from published
dates and prior-year patterns; verify on the firm's site.</p>
</body></html>
"""
)


def _cycle_note(cycles) -> str:
    if not cycles:
        return "—"
    parts = []
    for c in cycles:
        if c.status == CycleStatus.ROLLING:
            parts.append("rolling")
        elif c.status == CycleStatus.OPEN:
            parts.append("open")
        elif c.status == CycleStatus.NOT_YET_OPEN:
            parts.append(f"opens {c.opens_display()}")
        elif c.status == CycleStatus.CLOSED:
            parts.append("closed for cycle")
    return " · ".join(dict.fromkeys(parts)) or "—"


def _collect(settings: Settings):
    now = utcnow()
    fresh_cut = settings.fresh_days
    firms, fresh, stale = [], [], []
    for fc in settings.firms:
        st = load_state(fc.slug, fc.name)
        match_ct = review_ct = 0
        for p in st.tracked.values():
            if p.match_level == MatchLevel.REVIEW:
                review_ct += 1
                continue
            if p.match_level != MatchLevel.MATCH:
                continue
            match_ct += 1
            age = max((now - p.first_seen).days, 0)
            row = {
                "firm": fc.name, "title": p.title, "location": p.location, "url": p.url,
                "employment_type": p.employment_type, "comp_k": p.comp_k, "age_days": age,
            }
            is_fresh = not p.baseline and age <= fresh_cut
            (fresh if is_fresh else stale).append(row)
        firms.append({
            "name": fc.name, "slug": fc.slug, "enabled": fc.enabled, "tier": fc.tier,
            "match_count": match_ct, "review_count": review_ct,
            "failure_count": st.failure_count, "cycle_note": _cycle_note(fc.cycles),
        })
    fresh.sort(key=lambda r: (r["age_days"], -r["comp_k"]))
    stale.sort(key=lambda r: -r["comp_k"])
    firms.sort(key=lambda r: (-r["match_count"], r["name"]))
    return firms, fresh, stale


def _recent_history(limit: int = 40) -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text())
    except json.JSONDecodeError:
        return []
    return list(reversed(data))[:limit]


def render(settings: Settings, repo: str | None = None) -> None:
    repo = repo or DEFAULT_REPO
    firms, fresh, stale = _collect(settings)
    history = _recent_history()
    names = {f.slug: f.name for f in settings.firms}
    cycles_by_firm = {f.slug: f.cycles for f in settings.firms if f.cycles}
    soon = upcoming(cycles_by_firm, within_days=120, firm_names=names)

    data = {
        "repo": repo,
        "enabled_count": sum(1 for f in settings.firms if f.enabled),
        "fresh_days": settings.fresh_days,
        "soon": soon,
        "fresh": fresh,
        "stale": stale,
        "stale_firms": len({r["firm"] for r in stale}),
        "firms": firms,
        "history": history,
        "last_opening": history[0]["detected_at"] if history else "",
        "total_match": len(fresh) + len(stale),
    }

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "data.json").write_text(json.dumps(data, indent=2, default=str))
    (DOCS_DIR / "index.html").write_text(_TEMPLATE.render(**data))
