"""
Shared fixtures for orchestrator tests.
Spins up the MCP server in-process and points McpClient at it.
"""
import sys
import os
import pytest
import httpx
from fastapi.testclient import TestClient

# Make shared_models and mcp_server importable
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "mcp"))
sys.path.insert(0, os.path.join(REPO_ROOT, "orchestrator"))

from main import app as mcp_app  # noqa: E402 — mcp_server/main.py
from mcp_client import McpClient  # noqa: E402


class _TestTransport(httpx.AsyncBaseTransport):
    """Routes McpClient requests through the in-process TestClient."""

    def __init__(self, test_client: TestClient) -> None:
        self._client = test_client

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # Delegate to the sync TestClient (runs in the same thread)
        response = self._client.request(
            method=request.method,
            url=str(request.url),
            content=request.content,
            headers=dict(request.headers),
        )
        return httpx.Response(
            status_code=response.status_code,
            headers=dict(response.headers),
            content=response.content,
        )


@pytest.fixture(scope="session")
def mcp_test_client():
    """Session-scoped in-process MCP server."""
    with TestClient(mcp_app) as c:
        yield c


@pytest.fixture(scope="session")
def mcp(mcp_test_client):
    """McpClient wired to the in-process MCP server."""
    transport = _TestTransport(mcp_test_client)
    http = httpx.AsyncClient(base_url="http://testserver", transport=transport)
    client = McpClient.__new__(McpClient)
    client._http = http
    client._max_retries = 3
    client._backoff = (0.0, 0.0, 0.0)  # no sleep in tests
    return client
