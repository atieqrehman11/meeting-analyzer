from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger("shared_models.mcp_client")


class McpCallError(Exception):
    """Raised when an MCP tool call fails after all retries."""

    def __init__(self, code: str, message: str, retryable: bool) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(f"[{code}] {message}")


class BaseMcpClient:
    """Base MCP transport client with retry and error handling."""

    BASE = "/v1/tools"

    def __init__(
        self,
        base_url: str,
        max_retries: int = 3,
        backoff: tuple[float, ...] = (1.0, 2.0, 4.0),
        timeout: float = 30.0,
    ) -> None:
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self._max_retries = max_retries
        self._backoff = backoff
        self._last_response: dict[str, object] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "BaseMcpClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self.aclose()

    async def _post(
        self, path: str, payload: dict, *, expect_body: bool = True
    ) -> dict:
        url = f"{self.BASE}{path}"
        last_error: Optional[McpCallError] = None

        for attempt, delay in enumerate((*self._backoff, None)):
            error = await self._attempt(url, payload, expect_body, path, attempt)
            if error is None:
                return self._last_response
            last_error = error
            if not error.retryable or delay is None:
                raise error
            await asyncio.sleep(delay)

        raise last_error  # type: ignore[return-value]

    async def _attempt(
        self, url: str, payload: dict, expect_body: bool, path: str, attempt: int
    ) -> Optional[McpCallError]:
        try:
            resp = await self._http.post(url, json=payload)
        except httpx.TransportError as exc:
            logger.warning(
                "MCP transport error on %s (attempt %d): %s",
                path,
                attempt + 1,
                exc,
            )
            return McpCallError("TRANSPORT_ERROR", str(exc), retryable=True)

        if resp.status_code in (200, 204):
            self._last_response = resp.json() if expect_body and resp.content else {}
            return None

        error = self._parse_error(resp)
        if error.retryable:
            logger.warning(
                "MCP retryable error on %s (attempt %d): [%s] %s",
                path,
                attempt + 1,
                error.code,
                error.message,
            )
        return error

    @staticmethod
    def _parse_error(resp: httpx.Response) -> McpCallError:
        try:
            err = resp.json().get("error", {})
            return McpCallError(
                code=err.get("code", "UNKNOWN"),
                message=err.get("message", resp.text),
                retryable=err.get("retryable", False),
            )
        except Exception:
            return McpCallError("UNKNOWN", resp.text, retryable=False)
