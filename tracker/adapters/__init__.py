"""Adapters turn a firm's careers source into a list of RawPosting."""

from __future__ import annotations

from ..config import FirmConfig
from .ashby import AshbyAdapter
from .base import Adapter, AdapterError
from .beesite import BeesiteAdapter
from .glencore import GlencoreAdapter
from .greenhouse import GreenhouseAdapter
from .gs_higher import GsHigherAdapter
from .html_list import HtmlListAdapter
from .lever import LeverAdapter
from .oracle_orc import OracleOrcAdapter
from .phenom import PhenomAdapter
from .playwright_feed import PlaywrightFeedAdapter
from .radancy import RadancyAdapter
from .recruitee import RecruiteeAdapter
from .smartrecruiters import SmartRecruitersAdapter
from .successfactors import SuccessFactorsAdapter
from .teamtailor import TeamtailorAdapter
from .workable import WorkableAdapter
from .workday import WorkdayAdapter

_REGISTRY: dict[str, type[Adapter]] = {
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "ashby": AshbyAdapter,
    "smartrecruiters": SmartRecruitersAdapter,
    "workday": WorkdayAdapter,
    "oracle_orc": OracleOrcAdapter,
    "gs_higher": GsHigherAdapter,
    "beesite": BeesiteAdapter,
    "glencore": GlencoreAdapter,
    "playwright": PlaywrightFeedAdapter,
    "html": HtmlListAdapter,
    "workable": WorkableAdapter,
    "recruitee": RecruiteeAdapter,
    "teamtailor": TeamtailorAdapter,
    "radancy": RadancyAdapter,
    "successfactors": SuccessFactorsAdapter,
    "phenom": PhenomAdapter,
}


def get_adapter(firm: FirmConfig) -> Adapter:
    try:
        cls = _REGISTRY[firm.adapter]
    except KeyError:
        raise AdapterError(f"unknown adapter '{firm.adapter}' for firm '{firm.slug}'") from None
    return cls(firm)


__all__ = ["Adapter", "AdapterError", "get_adapter"]
