import mimetypes
import secrets
import time
from dataclasses import dataclass
from typing import Literal

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from config import onyx_url, user_agent
from onyx import AuthError, mcp, post_file_api


TRANSFER_TTL_SECONDS = 600  # 10 minutes to run the curl command
MAX_UPLOAD_BYTES = 100_000_000  # 100 MB cap


@dataclass
class PendingTransfer:
    kind: Literal["upload", "download"]
    pat: str
    expires_at: float
    purpose: Literal["submit", "return"] = "submit"
    vdi_id: int | None = None  # upload: which VDI to submit to
    filename: str | None = None  # upload: original filename
    file_id: int | None = None  # download: which Onyx file to stream


pending_transfers: dict[str, PendingTransfer] = {}


def create_transfer(transfer: PendingTransfer) -> str:
    """Stores a pending transfer and returns its unguessable single-use token.
    Expired entries are swept on every create — no background task needed."""
    purge_expired()
    token = secrets.token_urlsafe(32)
    pending_transfers[token] = transfer
    return token


def consume_transfer(token: str, kind: str) -> PendingTransfer | None:
    """Pop the pending transfer; None if unknown, expired, or the wrong kind
    (an upload token must not work on the download route, or vice versa).
    Single use."""
    transfer = pending_transfers.pop(token, None)
    if transfer is None or transfer.expires_at < time.time():
        return None
    if transfer.kind != kind:
        return None
    return transfer


def purge_expired() -> None:
    now = time.time()
    for token in [t for t, u in pending_transfers.items() if u.expires_at < now]:
        pending_transfers.pop(token, None)


@mcp.custom_route("/uploads/{token}", methods=["PUT"])
async def receive_upload(request: Request) -> JSONResponse:
    upload = consume_transfer(request.path_params["token"], "upload")
    if upload is None:
        return JSONResponse(
            {
                "error": "Upload link is invalid or expired. Ask the assistant "
                "to start the submission again."
            },
            status_code=404,
        )

    body = await request.body()
    if not body:
        return JSONResponse({"error": "No file bytes received."}, status_code=400)
    if len(body) > MAX_UPLOAD_BYTES:
        return JSONResponse({"error": "File exceeds the size limit."}, status_code=413)

    content_type = mimetypes.guess_type(upload.filename)[0] or "application/pdf"
    headers = {"Authorization": f"Bearer {upload.pat}", "User-Agent": user_agent}
    try:
        result = await post_file_api(
            f"vdi/{upload.vdi_id}/submit",
            body,
            upload.filename,
            content_type=content_type,
            headers=headers,
        )
    except AuthError:
        return JSONResponse(
            {
                "error": "Onyx rejected the stored credentials. Generate a new "
                "Personal Access Token, reconnect, and start the submission again."
            },
            status_code=502,
        )
    except httpx.HTTPStatusError as err:
        return JSONResponse(
            {"error": f"Onyx rejected the submission ({err.response.status_code})."},
            status_code=502,
        )
    except httpx.RequestError:
        return JSONResponse({"error": "Could not reach Onyx."}, status_code=502)

    return JSONResponse({"submitted": True, "vdi": result})


@mcp.custom_route("/downloads/{token}", methods=["GET"])
async def serve_download(request: Request) -> Response:
    download = consume_transfer(request.path_params["token"], "download")
    if download is None:
        return JSONResponse(
            {
                "error": "Download link is invalid or expired. Ask the assistant "
                "to start the download again."
            },
            status_code=404,
        )

    # Onyx's status must be checked before any bytes are relayed to the
    # caller, so the stream is opened manually (client.send(..., stream=True))
    # rather than inside a `with client.stream(...)` block. On the happy path
    # the client and response stay open for the life of the StreamingResponse
    # and are closed by the generator's `finally`; on every error path they
    # are closed here before returning JSON.
    headers = {"Authorization": f"Bearer {download.pat}", "User-Agent": user_agent}
    client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0))
    try:
        onyx_response = await client.send(
            client.build_request(
                "GET",
                f"{onyx_url}/api/files/{download.file_id}",
                params={"download": 1},
                headers=headers,
            ),
            stream=True,
        )
    except httpx.RequestError:
        await client.aclose()
        return JSONResponse({"error": "Could not reach Onyx."}, status_code=502)

    if onyx_response.status_code != 200:
        await onyx_response.aclose()
        await client.aclose()
        if onyx_response.status_code == 401:
            return JSONResponse(
                {
                    "error": "Onyx rejected the stored credentials. Generate a "
                    "new Personal Access Token, reconnect, and start the "
                    "download again."
                },
                status_code=502,
            )
        return JSONResponse(
            {"error": f"Onyx rejected the download ({onyx_response.status_code})."},
            status_code=502,
        )

    async def relay():
        try:
            async for chunk in onyx_response.aiter_bytes():
                yield chunk
        finally:
            await onyx_response.aclose()
            await client.aclose()

    response_headers = {
        name: onyx_response.headers[name]
        for name in ("content-type", "content-disposition")
        if name in onyx_response.headers
    }
    return StreamingResponse(relay(), headers=response_headers)
