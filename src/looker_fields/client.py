"""Async Looker API client using httpx."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


class LookerClient:
    """Async HTTP client for the Looker API with token management and rate limiting."""

    def __init__(self, settings: Settings, concurrency: int = 10) -> None:
        self.settings = settings
        self.semaphore = asyncio.Semaphore(concurrency)
        self._token: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> LookerClient:
        self._client = httpx.AsyncClient(
            base_url=self.settings.api_url,
            timeout=self.settings.looker_timeout,
            verify=self.settings.looker_verify_ssl,
            http2=True,
        )
        await self._authenticate()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            try:
                await self._client.delete("logout", headers=self._auth_headers)
            except Exception:
                pass
            await self._client.aclose()

    async def _authenticate(self) -> None:
        """Obtain an access token via client credentials."""
        assert self._client is not None
        resp = await self._client.post(
            "login",
            data={
                "client_id": self.settings.looker_client_id,
                "client_secret": self.settings.looker_client_secret,
            },
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        logger.info("Authenticated with Looker API")

    @property
    def _auth_headers(self) -> dict[str, str]:
        assert self._token is not None
        return {"Authorization": f"Bearer {self._token}"}

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Make a rate-limited GET request."""
        assert self._client is not None
        async with self.semaphore:
            resp = await self._client.get(path, params=params, headers=self._auth_headers)
            resp.raise_for_status()
            return resp.json()

    async def get_swagger(self) -> dict[str, Any]:
        """Fetch the OpenAPI/Swagger spec (health check + schema discovery)."""
        return await self.get("swagger.json")

    async def all_lookml_models(self) -> list[dict[str, Any]]:
        """Fetch all LookML models with their explores."""
        return await self.get(
            "lookml_models", params={"fields": "name,project_name,label,explores"}
        )

    async def lookml_model_explore(
        self, model_name: str, explore_name: str, fields: str | None = None
    ) -> dict[str, Any]:
        """Fetch a single explore's full metadata including all fields."""
        params: dict[str, Any] = {}
        if fields:
            params["fields"] = fields
        return await self.get(
            f"lookml_models/{model_name}/explores/{explore_name}", params=params
        )
