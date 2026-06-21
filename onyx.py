from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("onyx")


ONYX_URL = ""
USER_AGENT = "onyx-app/1.0"


async def get_api(path: str) -> dict | list:
    """Makes a get call to the api, raises error on failure. handle specific errors in tool"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        result = await client.get(f"{ONYX_URL}/api/{path}")
        result.raise_for_status()

    return result.json()


async def post_api(path: str, payload: dict | None = None) -> dict | list:
    """Makes a post call to the api, raises error on failure. handle specific errors in tool"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        result = await client.post(f"{ONYX_URL}/api/{path}", json=payload)
        result.raise_for_status()

    return result.json()


async def patch_api(path: str, payload: dict | None = None) -> dict | list:
    """Makes a patch call to the api, raises on error on failure. Handle specfic errors in tool."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        result = await client.patch(f"{ONYX_URL}/api/{path}", json=payload)
        result.raise_for_status()

    return result.json()
