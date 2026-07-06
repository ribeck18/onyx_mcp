import os

# config.py reads env vars at import time (and load_dotenv() will not override
# values already present in the environment), so these must be set before any
# app module is imported.
os.environ.setdefault("ONYX_URL", "http://onyx.test")
os.environ.setdefault("USER_AGENT", "onyx-app/test")
# localhost:8000 keeps the Host header within FastMCP's default DNS-rebinding
# allowlist (127.0.0.1:*, localhost:*, [::1]:*)
os.environ.setdefault("MCP_PUBLIC_URL", "http://localhost:8000")

from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


FAKE_PAT = "fake-pat-s3cret-do-not-leak"

ONYX_URL = os.environ["ONYX_URL"]
MCP_PUBLIC_URL = os.environ["MCP_PUBLIC_URL"]


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def app(anyio_backend):
    """The FastMCP streamable-http ASGI app, with its session manager running.

    Session-scoped because StreamableHTTPSessionManager.run() may only be
    entered once per FastMCP instance, and the mcp instance is module-level.
    """
    from onyx import mcp
    import projects  # noqa: F401  registers project tools
    import vdi  # noqa: F401  registers vdi tools (incl. submit_vdi)
    import transfers  # noqa: F401  registers the /uploads/{token} route

    application = mcp.streamable_http_app()
    async with mcp.session_manager.run():
        yield application


@pytest.fixture(autouse=True)
def clean_transfer_store():
    import transfers
    import vdi

    transfers.pending_transfers.clear()
    vdi.staged_vdi_returns.clear()
    yield
    transfers.pending_transfers.clear()
    vdi.staged_vdi_returns.clear()


@pytest.fixture
async def http_client(app):
    """Plain HTTP client against the in-process app, for the upload route."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=MCP_PUBLIC_URL
    ) as client:
        yield client


@asynccontextmanager
async def mcp_session(app, pat=FAKE_PAT):
    """An MCP client session speaking streamable-http to the in-process app,
    carrying the PAT as a bearer Authorization header."""

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=MCP_PUBLIC_URL,
        headers={"Authorization": f"Bearer {pat}"},
        timeout=10.0,
    ) as client:
        async with streamable_http_client(
            f"{MCP_PUBLIC_URL}/mcp", http_client=client
        ) as (read_stream, write_stream, _get_session_id):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session


@pytest.fixture
def onyx_mock():
    """Mocks Onyx at the outbound httpx layer. The in-process MCP clients use
    an explicit ASGITransport, which respx does not patch, so only the MCP's
    outbound calls to Onyx are intercepted."""
    with respx.mock(base_url=ONYX_URL, assert_all_called=False) as router:
        yield router
