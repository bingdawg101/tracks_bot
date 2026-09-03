"""Adapter protocol and shared HTTP helper."""

from __future__ import annotations

import asyncio

import httpx

from ..config import FirmConfig
from ..models import RawPosting


class AdapterError(Exception):
    """Raised when a source cannot be fetched or parsed. Treated as a fetch failure
    (never a 'roles closed' signal)."""


class Adapter:
    name: str = "base"

    def __init__(self, firm: FirmConfig) -> None:
        self.firm = firm
        self.source = firm.source

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:  # pragma: no cover
        raise NotImplementedError

    def _require(self, key: str) -> str:
        val = str(self.source.get(key, "")).strip()
        if not val:
            raise AdapterError(f"{self.firm.slug}: missing source.{key} in firms.yaml")
        return val

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        retries: int = 2,
        **kwargs,
    ) -> dict | list:
        return await self._request_json(client, "GET", url, retries=retries, **kwargs)

    async def _post_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        retries: int = 2,
        **kwargs,
    ) -> dict | list:
        return await self._request_json(client, "POST", url, retries=retries, **kwargs)

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        retries: int = 2,
        **kwargs,
    ) -> dict | list:
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = await client.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPError, ValueError) as exc:  # ValueError covers bad JSON
                last = exc
                if attempt < retries:
                    await asyncio.sleep(1.5 * (attempt + 1))
        raise AdapterError(f"{self.firm.slug}: {method} {url} failed: {last}") from last
