import httpx
from mcp.server.fastmcp import FastMCP

from config import onyx_url, user_agent


mcp = FastMCP("onyx")


class AuthError(Exception):
    """Raised when the caller's Personal Access Token is missing or rejected by the api."""


def _user_token() -> str:
    """Pulls the bearer token from the current request, raises AuthError if it is missing."""
    request = mcp.get_context().request_context.request
    authorization = (
        request.headers.get("authorization") if request is not None else None
    )
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise AuthError(
            "Authentication to Onyx failed: no Personal Access Token was supplied. Generate a new token and reconnect."
        )
    return authorization.split(" ", 1)[1]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_user_token()}", "User-Agent": user_agent}


def _raise_for_status(result: httpx.Response):
    """Raises AuthError on 401, defers to httpx for everything else."""
    if result.status_code == 401:
        raise AuthError(
            "Authentication to Onyx failed (401): your Personal Access Token is missing, expired, or revoked. Generate a new token and reconnect."
        )
    result.raise_for_status()


async def get_api(path: str) -> dict | list:
    """Makes a get call to the api, raises error on failure. handle specific errors in tool"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        result = await client.get(f"{onyx_url}/api/{path}", headers=_headers())
        _raise_for_status(result)

    return result.json()


async def post_api(path: str, payload: dict | None = None) -> dict | list:
    """Makes a post call to the api, raises error on failure. handle specific errors in tool"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        result = await client.post(
            f"{onyx_url}/api/{path}", json=payload, headers=_headers()
        )
        _raise_for_status(result)

    return result.json()


async def post_file_api(
    path: str,
    file_bytes: bytes,
    filename: str,
    content_type: str = "application/pdf",
    form_fields: dict | None = None,
    headers: dict | None = None,
) -> dict | list:
    """POSTs multipart/form-data to the api. Used for endpoints that take file
    uploads (vdi submit/return). Raises on failure like post_api. The headers
    override exists for callers outside a live tool call (e.g. the upload
    route), where the PAT comes from the pending-transfer store instead of the
    request context."""
    files = {"file": (filename, file_bytes, content_type)}
    async with httpx.AsyncClient(timeout=60.0) as client:
        result = await client.post(
            f"{onyx_url}/api/{path}",
            files=files,
            data=form_fields,
            headers=headers if headers is not None else _headers(),
        )
        _raise_for_status(result)

    return result.json()


async def patch_api(path: str, payload: dict | None = None) -> dict | list:
    """Makes a patch call to the api, raises on error on failure. Handle specfic errors in tool."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        result = await client.patch(
            f"{onyx_url}/api/{path}", json=payload, headers=_headers()
        )
        _raise_for_status(result)

    return result.json()
