from __future__ import annotations

import pytest

from tracker.config import FilterConfig


@pytest.fixture
def flt() -> FilterConfig:
    return FilterConfig(
        include=["trader", "trading", "quant", "quantitative", "research", "researcher"],
        exclude=["senior", "vice president", "head of"],
        locations=["london", "united kingdom"],
        departments=[],
        eligibility_terms=["graduate", "intern", "internship", "campus", "placement", "grad"],
        eligible_employment_types=["intern", "graduate", "new grad", "campus"],
        excluded_employment_types=["experienced", "permanent"],
    )
