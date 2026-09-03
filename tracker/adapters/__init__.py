"""Adapters turn a firm's careers source into a list of RawPosting."""

from __future__ import annotations

from ..config import FirmConfig
from .base import Adapter, AdapterError
from .greenhouse import GreenhouseAdapter
from .lever import LeverAdapter

_REGISTRY: dict[str, type[Adapter]] = {
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
}


def get_adapter(firm: FirmConfig) -> Adapter:
    try:
        cls = _REGISTRY[firm.adapter]
    except KeyError:
        raise AdapterError(f"unknown adapter '{firm.adapter}' for firm '{firm.slug}'") from None
    return cls(firm)


__all__ = ["Adapter", "AdapterError", "get_adapter"]
