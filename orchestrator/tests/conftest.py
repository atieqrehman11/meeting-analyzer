"""
Shared fixtures for orchestrator tests.
Spins up the MCP server in-process and points McpClient at it.
"""
import sys
from pathlib import Path
import pytest
import httpx
from fastapi.testclient import TestClient

# mcp/main.py is not an installed module — add mcp/ to path
_MCP_DIR = str(Path(__file__).resolve().parents[2] / "mcp")
if _MCP_DIR not in sys.path:
    sys.path.insert(0, _MCP_DIR)

from main import app as mcp_app  # mcp/main.py
from orchestrator.mcp_client import McpClient


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
