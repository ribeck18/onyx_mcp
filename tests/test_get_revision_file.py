"""End-to-end tests of the get_revision_file download flow: MCP tool call
through an in-process MCP client session, plain HTTP GET of the one-time
download URL, Onyx mocked at the outbound httpx layer with streamed bodies."""

import re
import time

import anyio
import httpx
import pytest

from conftest import FAKE_PAT, MCP_PUBLIC_URL, mcp_session
import transfers
from transfers import PendingTransfer


pytestmark = pytest.mark.anyio

SUBMIT_BYTES = b"%PDF-1.7 the submittal that went out"
RETURN_BYTES = b"%PDF-1.7 the buyer's return document"

REVISION = {
    "id": 3,
    "vendor_data_item_id": 7,
    "revision_number": 1,
    "submit_file": {
        "id": 21,
        "original_name": "weld-procedures.pdf",
        "content_type": "application/pdf",
    },
    "submitted_at": "2026-06-01T12:00:00Z",
    "return_file": {
        "id": 22,
        "original_name": "weld-procedures-returned.pdf",
        "content_type": "application/pdf",
    },
    "returned_at": "2026-06-15T12:00:00Z",
    "comments": None,
    "status": "returned",
    "created_at": "2026-06-01T12:00:00Z",
    "updated_at": "2026-06-15T12:00:00Z",
}

REVISION_NO_RETURN = {
    **REVISION,
    "return_file": None,
    "returned_at": None,
    "status": "submitted",
}


def tool_text(result) -> str:
    return "".join(block.text for block in result.content if block.type == "text")


def extract_download_url(text: str) -> str:
    match = re.search(rf"{re.escape(MCP_PUBLIC_URL)}/downloads/[\w\-]+", text)
    assert match, f"no download URL found in tool result:\n{text}"
    return match.group(0)


async def call_get_revision_file(app, vdi_id=7, revision_id=3, side="submittal"):
    async with mcp_session(app) as session:
        result = await session.call_tool(
            "get_revision_file",
            {"vdi_id": vdi_id, "revision_id": revision_id, "side": side},
        )
    return tool_text(result)


def mock_revision(onyx_mock, revision=REVISION, vdi_id=7, revision_id=3):
    onyx_mock.get(f"/api/vdi/{vdi_id}/revisions/{revision_id}").respond(
        200, json=revision
    )


class ChunkStream(httpx.AsyncByteStream):
    """A mocked streamed Onyx body: the bytes arrive as separate chunks, the
    way a real large file would, so the route must relay rather than buffer."""

    def __init__(self, chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


def mock_file(onyx_mock, file_id, chunks, filename, content_type="application/pdf"):
    return onyx_mock.get(f"/api/files/{file_id}", params={"download": "1"}).respond(
        200,
        stream=ChunkStream(chunks),
        headers={
            "content-type": content_type,
            "content-disposition": f'attachment; filename="{filename}"',
        },
    )


async def test_submittal_side_end_to_end(app, http_client, onyx_mock):
    mock_revision(onyx_mock)
    file_route = mock_file(
        onyx_mock, 21, [SUBMIT_BYTES[:10], SUBMIT_BYTES[10:]], "weld-procedures.pdf"
    )

    text = await call_get_revision_file(app, side="submittal")
    url = extract_download_url(text)
    # curl command names the original file for -o
    assert 'curl -sS -o "weld-procedures.pdf"' in text

    response = await http_client.get(url)

    assert response.status_code == 200
    assert response.content == SUBMIT_BYTES
    assert response.headers["content-type"] == "application/pdf"
    assert 'filename="weld-procedures.pdf"' in response.headers["content-disposition"]
    # The Onyx fetch used the stored PAT, invisible to the caller.
    assert file_route.called
    onyx_request = file_route.calls.last.request
    assert onyx_request.headers["authorization"] == f"Bearer {FAKE_PAT}"


async def test_return_side_end_to_end(app, http_client, onyx_mock):
    mock_revision(onyx_mock)
    mock_file(
        onyx_mock,
        22,
        [RETURN_BYTES[:7], RETURN_BYTES[7:20], RETURN_BYTES[20:]],
        "weld-procedures-returned.pdf",
    )

    text = await call_get_revision_file(app, side="return")
    assert 'curl -sS -o "weld-procedures-returned.pdf"' in text

    response = await http_client.get(extract_download_url(text))

    assert response.status_code == 200
    assert response.content == RETURN_BYTES
    assert (
        'filename="weld-procedures-returned.pdf"'
        in response.headers["content-disposition"]
    )


async def test_response_is_streamed_not_buffered(app, onyx_mock):
    """Drive the ASGI app directly (httpx's ASGITransport joins body parts, so
    it can't observe chunking): each Onyx chunk must arrive as its own
    http.response.body message, proving the route relays rather than buffers."""
    chunks = [b"one-", b"two-", b"three"]
    mock_file(onyx_mock, 21, chunks, "weld-procedures.pdf")
    stash_download("fresh-token", expires_in=600)

    messages = []
    request_sent = False

    async def receive():
        # First call delivers the (empty) request body; later calls park
        # forever so Starlette's listen_for_disconnect idles at a checkpoint
        # until the finished stream cancels it.
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await anyio.sleep_forever()

    async def send(message):
        messages.append(message)

    await app(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/downloads/fresh-token",
            "raw_path": b"/downloads/fresh-token",
            "query_string": b"",
            "headers": [(b"host", b"localhost:8000")],
            "server": ("localhost", 8000),
            "client": ("127.0.0.1", 12345),
        },
        receive,
        send,
    )

    start = next(m for m in messages if m["type"] == "http.response.start")
    assert start["status"] == 200
    body_messages = [
        m["body"]
        for m in messages
        if m["type"] == "http.response.body" and m.get("body")
    ]
    assert body_messages == chunks  # one ASGI message per Onyx chunk
    assert b"".join(body_messages) == b"one-two-three"


async def test_no_return_document_yet(app, onyx_mock):
    mock_revision(onyx_mock, revision=REVISION_NO_RETURN)

    text = await call_get_revision_file(app, side="return")

    assert "no return document yet" in text
    assert FAKE_PAT not in text
    assert transfers.pending_transfers == {}  # no token minted


async def test_revision_not_of_vdi(app, onyx_mock):
    # Onyx 404s both when the revision is missing and when it belongs to
    # another VDI — the tool relays a friendly message either way.
    onyx_mock.get("/api/vdi/7/revisions/99").respond(
        404, json={"detail": "Revision not found"}
    )

    text = await call_get_revision_file(app, revision_id=99)

    assert "could not be found" in text
    assert FAKE_PAT not in text
    assert transfers.pending_transfers == {}


async def test_instructions_and_no_pat_leak(app, onyx_mock):
    mock_revision(onyx_mock)

    text = await call_get_revision_file(app)

    assert FAKE_PAT not in text
    assert "user's machine" in text
    assert "curl.exe" in text
    assert "start over" in text


async def test_token_is_single_use(app, http_client, onyx_mock):
    mock_revision(onyx_mock)
    mock_file(onyx_mock, 21, [SUBMIT_BYTES], "weld-procedures.pdf")

    url = extract_download_url(await call_get_revision_file(app))

    first = await http_client.get(url)
    assert first.status_code == 200

    replay = await http_client.get(url)
    assert replay.status_code == 404


def stash_download(token: str, expires_in: float, file_id: int = 21) -> None:
    transfers.pending_transfers[token] = PendingTransfer(
        kind="download",
        pat=FAKE_PAT,
        expires_at=time.time() + expires_in,
        file_id=file_id,
    )


async def test_expired_token_indistinguishable_from_unknown(app, http_client):
    stash_download("expired-token", expires_in=-1)

    expired = await http_client.get("/downloads/expired-token")
    unknown = await http_client.get("/downloads/never-existed")

    assert expired.status_code == 404
    assert unknown.status_code == 404
    assert expired.content == unknown.content


async def test_upload_token_rejected_on_download_route(app, http_client):
    transfers.pending_transfers["upload-token"] = PendingTransfer(
        kind="upload",
        pat=FAKE_PAT,
        expires_at=time.time() + 600,
        vdi_id=7,
        filename="weld-procedures.pdf",
    )

    response = await http_client.get("/downloads/upload-token")
    unknown = await http_client.get("/downloads/never-existed")

    assert response.status_code == 404
    assert response.content == unknown.content


async def test_download_token_rejected_on_upload_route(app, http_client):
    stash_download("download-token", expires_in=600)

    wrong_kind = await http_client.put("/uploads/download-token", content=b"x")
    unknown = await http_client.put("/uploads/never-existed", content=b"x")

    assert wrong_kind.status_code == 404
    assert wrong_kind.content == unknown.content


async def test_onyx_404_surfaces_as_502(app, http_client, onyx_mock):
    onyx_mock.get("/api/files/21", params={"download": "1"}).respond(
        404, json={"detail": "File not found"}
    )
    stash_download("fresh-token", expires_in=600)

    response = await http_client.get("/downloads/fresh-token")

    assert response.status_code == 502
    assert "404" in response.json()["error"]
    assert FAKE_PAT not in response.text
