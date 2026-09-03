"""Render the static status dashboard (docs/index.html + docs/data.json).

Regenerated every run but only committed when its content actually changes, so the page's
timestamp reflects the last *meaningful* update. Live run health is shown via a shields.io
badge pointing at the Actions workflow, not via a per-run commit.
"""

from __future__ import annotations

import json

from jinja2 import Template

from .config import DOCS_DIR, HISTORY_FILE, Settings
from .diff import load_state
from .models import MatchLevel

# owner/repo — used for the Actions badge + run links. Overridden by GITHUB_REPOSITORY in CI.
DEFAULT_REPO = "bingdawg101/tracks_bot"

_TEMPLATE = Template(
    """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Careers Tracker</title>
<style>
  :root { color-scheme: light dark; --bg:#fff; --fg:#111; --muted:#666; --line:#e3e3e3;
    --match:#0a7d32; --review:#8a6d00; --fail:#b00020; --card:#fafafa; }
  @media (prefers-color-scheme: dark) { :root { --bg:#14151a; --fg:#e8e8e8; --muted:#9aa0a6;
    --line:#2a2c33; --match:#4ccf6f; --review:#e0b53d; --fail:#ff6b81; --card:#1c1d23; } }
  * { box-sizing: border-box; }
  body { margin:0; font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    background:var(--bg); color:var(--fg); padding:24px; max-width:1000px; margin:0 auto; }
  h1 { font-size:20px; margin:0 0 4px; } h2 { font-size:15px; margin:28px 0 10px; }
  .meta { color:var(--muted); font-size:13px; margin-bottom:16px; }
  a { color:inherit; } table { border-collapse:collapse; width:100%; font-size:13.5px; }
  th,td { text-align:left; padding:7px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
  th { color:var(--muted); font-weight:600; }
  .n { font-variant-numeric:tabular-nums; } .ok{color:var(--match)} .warn{color:var(--review)} .bad{color:var(--fail)}
  .pill { display:inline-block; padding:1px 7px; border-radius:10px; font-size:12px;
    border:1px solid var(--line); }
  ul.roles { margin:4px 0 0; padding-left:18px; } ul.roles li { margin:2px 0; }
  .tag { color:var(--muted); font-size:12px; }
  .hist li { margin:3px 0; } code { background:var(--card); padding:1px 4px; border-radius:4px; }
</style></head><body>
<h1>Careers Tracker</h1>
<div class="meta">
  Grad / final-year / internship roles &mdash; commodities, quant, S&amp;T, global markets &mdash; London/UK.<br>
  <img alt="last check" src="https://img.shields.io/github/actions/workflow/status/{{ repo }}/check.yml?label=last%20check&cacheSeconds=300">
  &middot; <a href="https://github.com/{{ repo }}/actions/workflows/check.yml">run history</a>
  {% if last_opening %}&middot; last opening detected {{ last_opening[:16] }} UTC{% endif %}
</div>

<h2>Open matching roles ({{ total_match }}) &middot; highest estimated pay first</h2>
<table>
<tr><th>Firm</th><th class="n">Top est.</th><th class="n">Match</th><th class="n">Review</th><th>Roles</th><th>Health</th></tr>
{% for f in firms %}
<tr>
  <td>{{ f.name }}{% if f.tier %}<br><span class="tag">{{ f.tier.replace('_',' ') }}</span>{% endif %}</td>
  <td class="n">{% if f.top_comp_k %}<b>£{{ f.top_comp_k }}k</b>{% else %}&mdash;{% endif %}</td>
  <td class="n">{{ f.match_count }}</td>
  <td class="n">{{ f.review_count }}</td>
  <td>
    {% if f.roles %}<ul class="roles">
      {% for r in f.roles %}<li>
        {% if r.comp_k %}<b>£{{ r.comp_k }}k</b> &middot; {% endif %}
        {% if r.url %}<a href="{{ r.url }}">{{ r.title }}</a>{% else %}{{ r.title }}{% endif %}
        <span class="tag">&mdash; {{ r.location }}{% if r.employment_type %} &middot; {{ r.employment_type }}{% endif %}</span>
      </li>{% endfor %}
    </ul>{% else %}<span class="tag">&mdash;</span>{% endif %}
  </td>
  <td>{% if f.failure_count %}<span class="bad">failing &times;{{ f.failure_count }}</span>
      {% else %}<span class="ok">ok</span>{% endif %}</td>
</tr>
{% endfor %}
</table>
<p class="tag">Pay figures are rough first-year total-comp estimates (London) by firm tier and role
family &mdash; for ranking, not gospel. Most firms don't publish salary.</p>

<h2>Recent openings</h2>
{% if history %}
<ul class="hist">
{% for h in history %}
  <li><code>{{ h.detected_at[:16] }}</code> &mdash;
    {% if h.comp_k %}<b>£{{ h.comp_k }}k</b> &middot; {% endif %}<b>{{ h.firm }}</b>:
    {% if h.url %}<a href="{{ h.url }}">{{ h.title }}</a>{% else %}{{ h.title }}{% endif %}
    <span class="tag">{{ h.location }}</span></li>
{% endfor %}
</ul>
{% else %}<div class="tag">Nothing detected yet &mdash; baseline established, watching for changes.</div>{% endif %}

</body></html>
"""
)


def _firm_rows(settings: Settings) -> list[dict]:
    rows = []
    for fc in settings.firms:
        st = load_state(fc.slug, fc.name)
        roles = []
        review = 0
        for p in st.tracked.values():
            if p.match_level == MatchLevel.MATCH:
                roles.append(
                    {
                        "title": p.title,
                        "location": p.location,
                        "url": p.url,
                        "employment_type": p.employment_type,
                        "comp_k": p.comp_k,
                        "comp_label": p.comp_label,
                    }
                )
            elif p.match_level == MatchLevel.REVIEW:
                review += 1
        roles.sort(key=lambda r: (-r["comp_k"], r["title"]))
        rows.append(
            {
                "name": fc.name,
                "slug": fc.slug,
                "enabled": fc.enabled,
                "tier": fc.tier,
                "match_count": len(roles),
                "review_count": review,
                "top_comp_k": roles[0]["comp_k"] if roles else 0,
                "roles": roles,
                "failure_count": st.failure_count,
            }
        )
    # Money first: firms with the highest-paying open role at the top.
    rows.sort(key=lambda r: (-r["top_comp_k"], -r["match_count"], r["name"]))
    return rows


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
    firms = _firm_rows(settings)
    history = _recent_history()

    # No per-run timestamp in the output — the file must change only when the tracked data
    # changes, so "no news" runs commit nothing. Freshness comes from the Actions badge.
    data = {
        "repo": repo,
        "firms": firms,
        "history": history,
        "last_opening": history[0]["detected_at"] if history else "",
        "total_match": sum(f["match_count"] for f in firms),
    }

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "data.json").write_text(json.dumps(data, indent=2, default=str))
    (DOCS_DIR / "index.html").write_text(_TEMPLATE.render(**data))
