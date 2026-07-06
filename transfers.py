import mimetypes
import secrets
import time
from dataclasses import dataclass
from typing import Literal

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import user_agent
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
