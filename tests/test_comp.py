from __future__ import annotations

from tracker.comp import estimate, role_family


def test_role_family_detection():
    assert role_family("2027 Quantitative Trader") == "quant_trading"
    assert role_family("Machine Learning Researcher") == "quant_research"
    assert role_family("Sales and Trading — Summer Analyst") == "sales_trading"
    assert role_family("Software Engineer") == "swe"
    assert role_family("Graduate Commodity Trading Analyst") in ("commercial", "trading")
    assert role_family("HR Coordinator") == "other"


def test_elite_prop_beats_bank_for_same_role():
    prop = estimate("elite_prop", "Quantitative Trader")
    bank = estimate("bank_bulge", "Quantitative Trader")
    assert prop.midpoint_k > bank.midpoint_k
    assert prop.low_k < prop.midpoint_k < prop.high_k


def test_internship_discount_is_tier_aware():
    prop_ft = estimate("elite_prop", "Quant Researcher").midpoint_k
    prop_intern = estimate("elite_prop", "Quant Researcher", internship=True).midpoint_k
    bank_ft = estimate("bank_bulge", "Markets Analyst").midpoint_k
    bank_intern = estimate("bank_bulge", "Markets Analyst", internship=True).midpoint_k
    assert prop_intern / prop_ft > bank_intern / bank_ft  # prop interns closer to parity


def test_unknown_tier_falls_back():
    est = estimate("", "Trader")
    assert est.midpoint_k > 0
