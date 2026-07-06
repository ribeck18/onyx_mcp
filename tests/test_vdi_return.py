"""End-to-end tests of the buyer's-return slice: stage_vdi_return →
finalize_vdi_return through an in-process MCP client session, plain HTTP PUT
of real bytes to the upload route, Onyx mocked at the outbound httpx layer."""

import re
import time

import pytest

from conftest import FAKE_PAT, MCP_PUBLIC_URL, mcp_session
import transfers
import vdi
from transfers import PendingTransfer


pytestmark = pytest.mark.anyio

PDF_BYTES = b"%PDF-1.7 fake buyer return document bytes"

VDI_SUBMITTED = {"id": 7, "name": "Weld Procedures", "status": "submitted"}
VDI_RETURNED_B = {"id": 7, "name": "Weld Procedures", "status": "b"}


def tool_text(result) -> str:
    return "".join(block.text for block in result.content if block.type == "text")


def extract_stage_key(text: str) -> str:
    match = re.search(r"stage key ([0-9a-f\-]{36})", text)
    assert match, f"no stage key found in tool result:\n{text}"
    return match.group(1)


def extract_upload_url(text: str) -> str:
    match = re.search(rf"{re.escape(MCP_PUBLIC_URL)}/uploads/[\w\-]+", text)
    assert match, f"no upload URL found in tool result:\n{text}"
    return match.group(0)


async def call_stage(app, vdi_id=7, return_code="b", filename="weld-return.pdf",
                     comments=None):
    args = {"vdi_id": vdi_id, "return_code": return_code, "filename": filename}
    if comments is not None:
        args["comments"] = comments
    async with mcp_session(app) as session:
        result = await session.call_tool("stage_vdi_return", args)
    return tool_text(result)


async def call_finalize(app, stage_key):
    async with mcp_session(app) as session:
        result = await session.call_tool(
            "finalize_vdi_return", {"stage_key": stage_key}
        )
    return tool_text(result)


async def test_return_flow_end_to_end(app, http_client, onyx_mock):
    onyx_mock.get("/api/vdi/7").respond(200, json=VDI_SUBMITTED)
    return_route = onyx_mock.post("/api/vdi/7/return").respond(
        200, json=VDI_RETURNED_B
    )

    staged = await call_stage(app, comments="Weld map is missing sheet 3.")

    # The summary names the VDI, the code with its meaning, comments, filename.
    assert "Weld Procedures" in staged
    assert "B" in staged and "rejected" in staged
    assert "Weld map is missing sheet 3." in staged
    assert "weld-return.pdf" in staged
    assert "approval" in staged

    finalized = await call_finalize(app, extract_stage_key(staged))
    url = extract_upload_url(finalized)

    response = await http_client.put(url, content=PDF_BYTES)

    assert response.status_code == 200
    payload = response.json()
    assert payload["returned"] is True
    assert payload["vdi"]["status"] == "b"

    # The forwarded request matches the Onyx contract: multipart `file` plus
    # form fields `return_code` (lowercase wire value) and `comments`.
    assert return_route.called
    request = return_route.calls.last.request
    assert request.headers["authorization"] == f"Bearer {FAKE_PAT}"
    assert request.headers["content-type"].startswith("multipart/form-data")
    body = request.content
    assert b'name="file"' in body
    assert b'filename="weld-return.pdf"' in body
    assert PDF_BYTES in body
    assert b'name="return_code"\r\n\r\nb\r\n' in body
    assert b'name="comments"\r\n\r\nWeld map is missing sheet 3.\r\n' in body


async def test_comments_omitted_from_form(app, http_client, onyx_mock):
    onyx_mock.get("/api/vdi/7").respond(200, json=VDI_SUBMITTED)
    return_route = onyx_mock.post("/api/vdi/7/return").respond(
        200, json={"id": 7, "name": "Weld Procedures", "status": "a"}
    )

    staged = await call_stage(app, return_code="a")
    assert "(none)" in staged  # summary notes there are no comments
    assert "approved" in staged

    finalized = await call_finalize(app, extract_stage_key(staged))
    response = await http_client.put(
        extract_upload_url(finalized), content=PDF_BYTES
    )

    assert response.status_code == 200
    body = return_route.calls.last.request.content
    assert b'name="return_code"\r\n\r\na\r\n' in body
    assert b'name="comments"' not in body


async def test_stage_refuses_when_vdi_missing(app, onyx_mock):
    onyx_mock.get("/api/vdi/999").respond(404, json={"detail": "not found"})

    text = await call_stage(app, vdi_id=999)

    assert "could not be found" in text
    assert FAKE_PAT not in text
    assert vdi.staged_vdi_returns == {}  # no stage stored


@pytest.mark.parametrize("status", ["not_started", "a", "b"])
async def test_stage_refuses_when_not_returnable(app, onyx_mock, status):
    onyx_mock.get("/api/vdi/7").respond(
        200, json={"id": 7, "name": "Weld Procedures", "status": status}
    )

    text = await call_stage(app)

    assert "cannot be returned" in text
    assert status in text
    assert FAKE_PAT not in text
    assert vdi.staged_vdi_returns == {}  # no stage stored


async def test_finalize_unknown_stage_key(app):
    text = await call_finalize(app, "not-a-real-stage-key")

    assert "No staged return" in text
    assert "stage_vdi_return" in text  # tells the agent how to recover
    assert transfers.pending_transfers == {}  # no token minted


async def test_no_secret_leaks(app, onyx_mock):
    onyx_mock.get("/api/vdi/7").respond(200, json=VDI_SUBMITTED)

    staged = await call_stage(app, comments="Looks good.")
    stage_key = extract_stage_key(staged)

    # The user-facing summary block (the indented lines) never carries the
    # stage key — it only appears in the agent-directed instruction line,
    # which explicitly forbids showing it.
    summary_lines = [l for l in staged.splitlines() if l.startswith("  ")]
    assert summary_lines, "expected an indented summary block"
    assert all(stage_key not in line for line in summary_lines)
    assert "Do not show the stage key to the user" in staged
    assert FAKE_PAT not in staged

    finalized = await call_finalize(app, stage_key)
    assert FAKE_PAT not in finalized
    assert stage_key not in finalized


async def test_finalize_consumes_stage(app, onyx_mock):
    onyx_mock.get("/api/vdi/7").respond(200, json=VDI_SUBMITTED)

    stage_key = extract_stage_key(await call_stage(app))
    first = await call_finalize(app, stage_key)
    assert f"{MCP_PUBLIC_URL}/uploads/" in first

    replay = await call_finalize(app, stage_key)
    assert "No staged return" in replay
    assert len(transfers.pending_transfers) == 1  # no second token minted


def stash_return_transfer(token: str) -> None:
    transfers.pending_transfers[token] = PendingTransfer(
        kind="upload",
        pat=FAKE_PAT,
        expires_at=time.time() + 600,
        purpose="return",
        vdi_id=7,
        filename="weld-return.pdf",
        return_code="b",
        comments=None,
    )


async def test_return_token_is_single_use(app, http_client, onyx_mock):
    onyx_mock.post("/api/vdi/7/return").respond(200, json=VDI_RETURNED_B)
    stash_return_transfer("return-token")

    first = await http_client.put("/uploads/return-token", content=PDF_BYTES)
    assert first.status_code == 200

    replay = await http_client.put("/uploads/return-token", content=PDF_BYTES)
    assert replay.status_code == 404


async def test_return_token_rejected_on_wrong_kind_route(app, http_client):
    stash_return_transfer("return-token")

    response = await http_client.get("/downloads/return-token")

    assert response.status_code == 404


async def test_onyx_409_surfaces_as_502(app, http_client, onyx_mock):
    onyx_mock.post("/api/vdi/7/return").respond(
        409, json={"detail": "VDI cannot be returned from its current status"}
    )
    stash_return_transfer("return-token")

    response = await http_client.put("/uploads/return-token", content=PDF_BYTES)

    assert response.status_code == 502
    assert "409" in response.json()["error"]
    assert FAKE_PAT not in response.text
