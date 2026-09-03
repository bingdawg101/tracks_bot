"""Rough first-year total-compensation estimates, for ranking roles by money.

Most finance/commodity employers don't publish pay, so this is a heuristic: a lookup by
(firm tier x role family), London, first year (base + expected bonus / sign-on), in GBP.
It is deliberately coarse — good enough to sort "apply to this first" — and always returns
a wide range plus the midpoint used for sorting.

Firm tier comes from `tier:` in firms.yaml. Role family is inferred from the title.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Role families, matched against title + department (first hit wins, so order matters).
_FAMILY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("quant_trading", re.compile(r"\bquant\w*\s+trad|\btrader\b.*\bquant|\bsystematic\b", re.IGNORECASE)),
    ("quant_research", re.compile(r"\bquant\w*\s+research|\bresearch\w*\b.*\bquant|\bml\b|\bmachine learning\b|\bstrat(s|egist)\b", re.IGNORECASE)),
    ("sales_trading", re.compile(r"\bsales\s*(and|&|/)?\s*trading\b|\bglobal markets\b|\bficc\b|\bequities\b|\bfixed income\b|\bderivatives\b|\bs&t\b", re.IGNORECASE)),
    ("trading", re.compile(r"\btrad(er|ing)\b|\bmarket maker|\bmarket making\b|\bportfolio manager\b|\bexecution\b", re.IGNORECASE)),
    ("structuring", re.compile(r"\bstructur(ing|er)\b|\borigination\b", re.IGNORECASE)),
    ("commercial", re.compile(r"\bcommercial\b|\bmerchandis|\btrading analyst\b|\bcommodity analyst\b|\bcommodit\w+ trad", re.IGNORECASE)),
    ("swe", re.compile(r"\b(software|systems|platform|hardware|fpga|network|infra\w*|devops|data)\s+engineer|\bdeveloper\b|\bsde\b|\bswe\b", re.IGNORECASE)),
    ("risk_ops", re.compile(r"\brisk\b|\boperations\b|\bmiddle office\b|\bback office\b|\bsettlement|\bcompliance\b|\baudit\b|\bfinance\b|\baccounting\b", re.IGNORECASE)),
]

# Midpoint £k, first-year total, London grad/new-grad. Internships priced near-parity
# (elite prop interns are paid similar monthly rates; banks a bit less — see _intern_factor).
_TABLE: dict[str, dict[str, int]] = {
    #                 q_trade q_res  trading s_trade struct commerc swe   risk_ops other
    "elite_prop":    {"quant_trading": 190, "quant_research": 180, "trading": 170,
                      "sales_trading": 150, "structuring": 150, "commercial": 150,
                      "swe": 140, "risk_ops": 95, "other": 110},
    "hedge_fund":    {"quant_trading": 160, "quant_research": 155, "trading": 140,
                      "sales_trading": 120, "structuring": 120, "commercial": 120,
                      "swe": 120, "risk_ops": 85, "other": 95},
    "bank_bulge":    {"quant_trading": 95, "quant_research": 95, "trading": 90,
                      "sales_trading": 85, "structuring": 85, "commercial": 80,
                      "swe": 70, "risk_ops": 58, "other": 62},
    "bank_other":    {"quant_trading": 80, "quant_research": 80, "trading": 78,
                      "sales_trading": 72, "structuring": 72, "commercial": 68,
                      "swe": 62, "risk_ops": 52, "other": 55},
    "commodity_major": {"quant_trading": 130, "quant_research": 120, "trading": 130,
                        "sales_trading": 110, "structuring": 110, "commercial": 110,
                        "swe": 85, "risk_ops": 58, "other": 65},
    "commodity_other": {"quant_trading": 95, "quant_research": 90, "trading": 90,
                        "sales_trading": 80, "structuring": 80, "commercial": 78,
                        "swe": 70, "risk_ops": 50, "other": 55},
    "energy_utility": {"quant_trading": 85, "quant_research": 80, "trading": 78,
                       "sales_trading": 70, "structuring": 70, "commercial": 68,
                       "swe": 65, "risk_ops": 48, "other": 52},
}

_DEFAULT_TIER = "bank_other"


@dataclass
class CompEstimate:
    midpoint_k: int          # £k, used for sorting
    low_k: int
    high_k: int
    family: str
    basis: str               # short human note

    @property
    def label(self) -> str:
        return f"~£{self.midpoint_k}k (est. £{self.low_k}–{self.high_k}k)"


def role_family(title: str, department: str = "") -> str:
    hay = f"{title} {department}"
    for fam, pat in _FAMILY_PATTERNS:
        if pat.search(hay):
            return fam
    return "other"


def estimate(tier: str, title: str, department: str = "", *, internship: bool = False) -> CompEstimate:
    tier = tier if tier in _TABLE else _DEFAULT_TIER
    fam = role_family(title, department)
    mid = _TABLE[tier].get(fam, _TABLE[tier]["other"])

    factor = _intern_factor(tier) if internship else 1.0
    mid = round(mid * factor)
    # Range: ±35% for prop/HF (bonus-heavy, high variance), ±20% for banks.
    spread = 0.38 if tier in ("elite_prop", "hedge_fund", "commodity_major") else 0.22
    low, high = round(mid * (1 - spread)), round(mid * (1 + spread))
    basis = f"{tier.replace('_', ' ')} · {fam.replace('_', ' ')}"
    if internship:
        basis += " · internship"
    return CompEstimate(mid, low, high, fam, basis)


def _intern_factor(tier: str) -> float:
    # Elite prop interns are paid close to full monthly rate; banks pay interns less.
    return {"elite_prop": 0.92, "hedge_fund": 0.88, "commodity_major": 0.8}.get(tier, 0.7)
