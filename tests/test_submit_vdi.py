"""End-to-end tests of the submit_vdi tracer bullet: MCP tool call through an
in-process MCP client session, plain HTTP PUT of real bytes to the upload
route, Onyx mocked at the outbound httpx layer."""

import json
import re
import time

import httpx
import pytest

from conftest import FAKE_PAT, MCP_PUBLIC_URL, mcp_session
import transfers
from transfers import PendingTransfer


pytestmark = pytest.mark.anyio

PDF_BYTES = b"%PDF-1.7 fake construction submittal bytes"

VDI_NOT_STARTED = {"id": 7, "name": "Weld Procedures", "status": "not_started"}
VDI_SUBMITTED = {"id": 7, "name": "Weld Procedures", "status": "submitted"}


def tool_text(result) -> str:
    return "".join(block.text for block in result.content if block.type == "text")


def extract_upload_url(text: str) -> str:
    match = re.search(rf"{re.escape(MCP_PUBLIC_URL)}/uploads/[\w\-]+", text)
    assert match, f"no upload URL found in tool result:\n{text}"
    return match.group(0)


async def call_submit_vdi(app, vdi_id=7, filename="weld-procedures.pdf"):
    async with mcp_session(app) as session:
        result = await session.call_tool(
            "submit_vdi", {"vdi_id": vdi_id, "filename": filename}
        )
    return tool_text(result)


async def test_submit_flow_end_to_end(app, http_client, onyx_mock):
    onyx_mock.get("/api/vdi/7").respond(200, json=VDI_NOT_STARTED)
    submit_route = onyx_mock.post("/api/vdi/7/submit").respond(200, json=VDI_SUBMITTED)

    text = await call_submit_vdi(app)
    url = extract_upload_url(text)

    response = await http_client.put(url, content=PDF_BYTES)

    assert response.status_code == 200
    payload = response.json()
    assert payload["submitted"] is True
    assert payload["vdi"]["status"] == "submitted"

    # The forwarded request matches the Onyx contract: multipart with a single
    # `file` field, original filename, derived content type, stored PAT.
    assert submit_route.called
    request = submit_route.calls.last.request
    assert request.headers["authorization"] == f"Bearer {FAKE_PAT}"
    assert request.headers["content-type"].startswith("multipart/form-data")
    body = request.content
    assert body.count(b"Content-Disposition") == 1
    assert b'name="file"' in body
    assert b'filename="weld-procedures.pdf"' in body
    assert b"Content-Type: application/pdf" in body
    assert PDF_BYTES in body


async def test_instructions_and_no_pat_leak(app, onyx_mock):
    onyx_mock.get("/api/vdi/7").respond(200, json=VDI_NOT_STARTED)

    text = await call_submit_vdi(app)

    assert FAKE_PAT not in text
    # pre-upload user confirmation
    assert "confirmation" in text and "BEFORE uploading" in text
    # run on the machine that has the file
    assert "machine that has the file" in text
    # Windows curl.exe caveat
    assert "curl.exe" in text
    # expired-link recovery
    assert "start over" in text


async def test_refuses_when_vdi_missing(app, onyx_mock):
    onyx_mock.get("/api/vdi/999").respond(404, json={"detail": "not found"})

    text = await call_submit_vdi(app, vdi_id=999)

    assert "could not be found" in text
    assert FAKE_PAT not in text
    assert transfers.pending_transfers == {}  # no token minted


@pytest.mark.parametrize("status", ["submitted", "a", "d"])
async def test_refuses_when_not_submittable(app, onyx_mock, status):
    onyx_mock.get("/api/vdi/7").respond(200, json={"id": 7, "status": status})

    text = await call_submit_vdi(app)

    assert "cannot be submitted" in text
    assert status in text
    assert FAKE_PAT not in text
    assert transfers.pending_transfers == {}  # no token minted


async def test_token_is_single_use(app, http_client, onyx_mock):
    onyx_mock.get("/api/vdi/7").respond(200, json=VDI_NOT_STARTED)
    onyx_mock.post("/api/vdi/7/submit").respond(200, json=VDI_SUBMITTED)

    url = extract_upload_url(await call_submit_vdi(app))

    first = await http_client.put(url, content=PDF_BYTES)
    assert first.status_code == 200

    replay = await http_client.put(url, content=PDF_BYTES)
    assert replay.status_code == 404


def stash_transfer(token: str, expires_in: float) -> None:
    transfers.pending_transfers[token] = PendingTransfer(
        kind="upload",
        pat=FAKE_PAT,
        expires_at=time.time() + expires_in,
        vdi_id=7,
        filename="weld-procedures.pdf",
    )


async def test_expired_token_indistinguishable_from_unknown(app, http_client):
    stash_transfer("expired-token", expires_in=-1)

    expired = await http_client.put("/uploads/expired-token", content=PDF_BYTES)
    unknown = await http_client.put("/uploads/never-existed", content=PDF_BYTES)

    assert expired.status_code == 404
    assert unknown.status_code == 404
    assert expired.content == unknown.content


async def test_empty_body_returns_400(app, http_client):
    stash_transfer("fresh-token", expires_in=600)

    response = await http_client.put("/uploads/fresh-token", content=b"")

    assert response.status_code == 400


async def test_oversized_body_returns_413(app, http_client, monkeypatch):
    monkeypatch.setattr(transfers, "MAX_UPLOAD_BYTES", 10)
    stash_transfer("fresh-token", expires_in=600)

    response = await http_client.put("/uploads/fresh-token", content=b"x" * 11)

    assert response.status_code == 413


async def test_onyx_rejection_surfaces_as_502(app, http_client, onyx_mock):
    onyx_mock.post("/api/vdi/7/submit").respond(
        409, json={"detail": "VDI cannot be submitted from its current status"}
    )
    stash_transfer("fresh-token", expires_in=600)

    response = await http_client.put("/uploads/fresh-token", content=PDF_BYTES)

    assert response.status_code == 502
    assert "409" in response.json()["error"]
    assert FAKE_PAT not in response.text


async def test_content_type_derived_from_filename(app, http_client, onyx_mock):
    onyx_mock.get("/api/vdi/7").respond(200, json=VDI_NOT_STARTED)
    submit_route = onyx_mock.post("/api/vdi/7/submit").respond(200, json=VDI_SUBMITTED)

    url = extract_upload_url(await call_submit_vdi(app, filename="photo.png"))
    response = await http_client.put(url, content=b"not really a png")

    assert response.status_code == 200
    body = submit_route.calls.last.request.content
    assert b'filename="photo.png"' in body
    assert b"Content-Type: image/png" in body
