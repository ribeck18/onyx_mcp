# Plan: Submitting PDF revisions to a VDI through the MCP

## Goal

An agent using the onyx MCP can attach a PDF to a vendor data item by opening a new
revision — calling Onyx's existing `POST /api/vdi/{vdi_id}/submit` endpoint — without
the agent ever seeing the user's PAT, and in a way that works both when the MCP runs
on localhost and when it is hosted on a server.

## Background facts (verified against the Onyx codebase)

- `POST /api/vdi/{vdi_id}/submit` accepts **multipart/form-data** with a single field
  `file`. It stores the file and opens the next Revision (revision number, timestamp,
  and SUBMITTED status are all server-set). There is no JSON variant.
- The endpoint returns **409** if the VDI is not in a submittable status, **400** if
  the file is empty, **404** if the VDI does not exist, **401** on a bad/missing PAT.
- The sibling endpoint `POST /api/vdi/{vdi_id}/return` records the buyer's return:
  multipart `file`, form field `return_code` (A/B/C/D), optional form field `comments`.
- The MCP's existing `post_api` helper only sends JSON; multipart needs a new helper.
- The MCP reads the PAT per-request from the `Authorization` header via
  `_user_token()` in `onyx.py`. That only works *during a tool call* — this matters
  for Phase 2, where the upload arrives outside any tool call.

## The core problem

When the MCP is hosted remotely, the PDF lives on the user's machine and the server
cannot read a `file_path`. The bytes must cross the network. The chosen design (and
what was ruled out):

- ❌ Base64 in the tool argument — PDFs are 1–50 MB; blows message limits and tokens.
- ❌ Agent uploads straight to Onyx with the PAT — the PAT would leak into the
  agent's context/shell history. Explicitly rejected.
- ❌ A `file_path` tool argument the server reads off its own disk — on a multi-user
  hosted server this is an arbitrary-file-read exfiltration channel (any PAT holder
  could submit `/home/onyx/.env` to Onyx and download it back). Explicitly rejected,
  even as a dev-only mode; the staged upload works identically on localhost.
- ✅ **Staged upload through the MCP server**: a tool mints a short-lived, single-use
  upload URL on the MCP server itself. The agent sends the PDF there with `curl` — no
  credential needed, the random URL *is* the authorization and it is disposable. The
  MCP server forwards the bytes to Onyx using the PAT it captured during the original
  tool call. The PAT never leaves the server.
- ❌ A `file_url` fetch-by-reference mode — cut; see Phase 3 for the reasoning
  (agents fetch URLs locally; server-side fetch is an SSRF vector for no gain).

## Architecture (hosted flow)

```
Agent (user's machine)                 MCP server                        Onyx
       |                                    |                              |
       |-- tool: submit_vdi --------------->|                              |
       |      (vdi_id, filename)            |-- GET /api/vdi/{id} -------->|  validate VDI exists,
       |                                    |<-- 200, status check --------|  status is submittable
       |                                    |                              |
       |                                    | mint token, store            |
       |                                    | {token -> pat, vdi_id, exp}  |
       |<-- upload URL + curl instructions -|                              |
       |                                    |                              |
       |-- curl -T file.pdf PUT /upload/<token> -->                        |
       |                                    | look up token, consume it    |
       |                                    |-- POST /api/vdi/{id}/submit ->  multipart, PAT header
       |                                    |<-- 200 VdiRead --------------|
       |<-- JSON result of the submit ------|                              |
```

Deployment constraints (decided):

- **Single process, always.** The pending-transfer store is an in-memory dict, which
  only works when one process serves all requests. Run uvicorn with exactly one
  worker and never scale horizontally — with ≤4 users this server (which mostly
  waits on Onyx) needs nothing more. If that ever changes, swap the dict for Redis
  behind the `create_transfer`/`consume_transfer` seam; nothing else moves.
- **Same VPS as Onyx.** The MCP will be co-hosted with the Onyx web app. This means
  `ONYX_URL` can point at localhost (MCP→Onyx traffic never leaves the machine), and
  whatever reverse proxy already fronts Onyx also terminates TLS for the MCP's
  public URL. It also means any future feature that makes the server fetch
  agent-supplied URLs is an SSRF risk against Onyx itself — one reason the
  `file_url` mode was cut (Phase 3).

Design choices baked into this:

1. **One-shot forward** — the upload handler forwards to Onyx immediately when the
   bytes arrive and returns Onyx's response. No `finalize` tool call, no staged files
   on disk, nothing to clean up except expired map entries.
2. **Token map is in-memory** — `dict[token] -> {pat, vdi_id, filename, expires_at}`,
   same spirit as the existing `staged_projects` dict. Restarting the server just
   invalidates pending uploads, which is fine.
3. **Validate before minting** — the tool checks the VDI exists and is submittable
   *before* handing out an upload URL, so the agent gets a clear error up front
   instead of after uploading megabytes.

---

## Phase 1 — Multipart helper

The foundation everything else reuses. There is deliberately **no local `file_path`
mode** (see "The core problem" above): the staged upload in Phase 2 is the only way
bytes enter the server, in every deployment.

### 1.1 Add a multipart helper to `onyx.py`

Next to `post_api`, add:

```python
async def post_file_api(
    path: str,
    file_bytes: bytes,
    filename: str,
    content_type: str = "application/pdf",
    form_fields: dict | None = None,
    headers: dict | None = None,
) -> dict | list:
    """POSTs multipart/form-data to the api. Used for endpoints that take file
    uploads (vdi submit/return). Raises on failure like post_api."""
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
```

Notes:
- `timeout=60.0`, not 10.0 — big PDFs over a slow link need it.
- The `headers` override parameter exists for Phase 2, where the PAT comes from the
  token map instead of the live request context (`_headers()` only works during a
  tool call).
- Do **not** set a `Content-Type` header yourself; httpx sets the multipart boundary.

### 1.2 Content-type detection (small nicety)

Derive content type from the filename suffix (`mimetypes.guess_type`) with
`application/pdf` as the sensible default, since the documents will almost always
be PDFs.

Error handling follows the existing house style everywhere in this plan:
`AuthError` → message string, known status codes → friendly message, everything
else re-raised.

---

## Phase 2 — Staged upload for the hosted deployment

### 2.1 New config

Add to `config.py` / `.env`:

- `MCP_PUBLIC_URL` — the externally reachable base URL of the MCP server
  (e.g. `https://mcp.example.com`). Used to build upload URLs. For local testing,
  `http://localhost:8000`.

### 2.2 The pending-transfer store (new file, e.g. `transfers.py`)

One store serves both directions — uploads (Phase 2) and downloads (Phase 5) —
distinguished by a `kind` field, so the token/TTL/single-use machinery is built
and tested once.

```python
import secrets, time
from dataclasses import dataclass
from typing import Literal

TRANSFER_TTL_SECONDS = 600      # 10 minutes to run the curl command
MAX_UPLOAD_BYTES = 100_000_000  # 100 MB cap

@dataclass
class PendingTransfer:
    kind: Literal["upload", "download"]
    pat: str
    expires_at: float
    vdi_id: int | None = None     # upload: which VDI to submit to
    filename: str | None = None   # upload: original filename
    file_id: int | None = None    # download: which Onyx file to stream

pending_transfers: dict[str, PendingTransfer] = {}

def create_transfer(transfer: PendingTransfer) -> str:
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
```

Security properties to preserve when implementing:
- `secrets.token_urlsafe(32)` — unguessable; the URL is the whole authorization.
- **Single use**: `pop`, not `get`, so a token can never be replayed.
- **Kind-checked**: an upload token is worthless on the download route and vice
  versa.
- TTL enforced at consumption *and* swept by `purge_expired()` (called inside
  `create_transfer` — no background task needed at this scale).
- The map holds PATs in plain memory. Accepted trade-off: it is the same class of
  secret-handling as the server already does per-request, scoped to a 10-minute TTL.
  Never log the map, tokens, or PATs.

### 2.3 The upload route in `onyx.py`

FastMCP exposes the underlying Starlette app for extra routes via
`@mcp.custom_route` (verified present in the installed SDK, `mcp` 1.28.0):

```python
from starlette.requests import Request
from starlette.responses import JSONResponse

@mcp.custom_route("/uploads/{token}", methods=["PUT"])
async def receive_upload(request: Request) -> JSONResponse:
    upload = consume_upload(request.path_params["token"])
    if upload is None:
        return JSONResponse(
            {"error": "Upload link is invalid or expired. Ask the assistant "
                      "to start the submission again."},
            status_code=404,
        )

    body = await request.body()
    if not body:
        return JSONResponse({"error": "No file bytes received."}, status_code=400)
    if len(body) > MAX_UPLOAD_BYTES:
        return JSONResponse({"error": "File exceeds the size limit."}, status_code=413)

    headers = {"Authorization": f"Bearer {upload.pat}", "User-Agent": user_agent}
    try:
        result = await post_file_api(
            f"vdi/{upload.vdi_id}/submit", body, upload.filename, headers=headers
        )
    except httpx.HTTPStatusError as err:
        return JSONResponse(
            {"error": f"Onyx rejected the submission ({err.response.status_code})."},
            status_code=502,
        )
    except httpx.RequestError:
        return JSONResponse({"error": "Could not reach Onyx."}, status_code=502)

    return JSONResponse({"submitted": True, "vdi": result})
```

Notes:
- `PUT` with a raw body (`curl -T file.pdf <url>`) is simpler for agents than
  multipart — one flag, no field names. The route re-wraps the bytes as multipart
  when forwarding to Onyx.
- 404 for unknown *and* expired tokens (indistinguishable on purpose).
- The 413 size check above buffers the whole body first; if the SDK/Starlette version
  allows, prefer streaming `request.stream()` with an incremental count so an
  oversized upload is cut off early rather than buffered.

### 2.4 The tool

```python
@mcp.tool()
async def submit_vdi(vdi_id: int, filename: str) -> str:
    """Submits a document to a vendor data item, opening its next revision.
    Returns a one-time upload URL and a curl command. Before running that
    command, state to the user exactly which file you are about to submit and
    to which vendor data item, and get their confirmation — a submittal is
    permanent revision history and cannot be unsent. Run the command on the
    machine that has the file; the submission completes when the upload
    finishes. The upload URL expires in 10 minutes and works exactly once.
    Never show the user primary keys.
    """
```

Behavior:
1. Validate the VDI first: `get_api(f"vdi/{vdi_id}")`, check `status` is
   submittable, return the friendly 404/409 message early if not.
2. `token = create_upload(_user_token(), vdi_id, filename)` and return
   instructions the agent can act on directly:

```
Upload link created (expires in 10 minutes, single use).

BEFORE uploading: tell the user which file you are submitting and to which
vendor data item, and wait for their confirmation. A submittal is permanent
revision history.

Then run this on the machine that has the file (not in a remote sandbox):

    curl -sS -T "<local path to file>" "{MCP_PUBLIC_URL}/uploads/{token}"

On Windows/PowerShell use `curl.exe` (plain `curl` is an alias for
Invoke-WebRequest and takes different flags).

The response will confirm the revision was opened. Then verify with
get_revisions_for_vdi if needed.
```

Audience note (decided): all users connect through shell-capable agents (Claude
Cowork / opencode), so this output is written for the *agent* to act on — the user
never needs to see the URL. If a browser-only client ever appears, a small HTML
upload form served at `GET /uploads/{token}` can be added without changing the
token design.

The PAT is captured inside the tool call via `_user_token()` — the one place the
request context is live — and stored against the token. The agent only ever sees
the token URL.

### 2.5 Verify Phase 2

- Happy path: tool call → curl the returned URL with a PDF → 200, revision
  visible in Onyx.
- Replay the same URL → 404.
- Wait past the TTL (temporarily set TTL to ~5 s for the test) → 404.
- Upload to a made-up token → 404.
- VDI already submitted → tool refuses *before* minting a URL.
- Oversized file → 413.
- Two different users/PATs staging uploads concurrently → each submission lands
  as the right user (check Onyx audit/ownership if recorded).

---

## Phase 3 — `file_url` mode (fetch-by-reference) — CUT, do not build

Considered and deliberately rejected (do not re-add casually):

- Every user connects through a shell-capable agent, which can fetch a URL locally
  (`curl -o`) and feed the file through the staged upload — the mode saves nothing.
- The URLs that matter (SharePoint, vendor portals, email links) are authenticated;
  an anonymous server-side GET yields a login page, while the user's machine — where
  their browser session lives — fetches them fine.
- Server-side fetching is an SSRF vector, and the MCP shares a VPS with Onyx, so the
  guardrail code (DNS resolution checks, private-range rejection, redirect
  re-validation) would be mandatory and fiddly. Cutting the feature deletes the
  MCP's riskiest code path.

The supported pattern for documents-as-links: the agent downloads the file locally,
then uses the normal staged upload.

---

## Phase 4 — downloading revision documents

The mirror image of Phase 2, reusing the same store. (Replaces the two `-> bytes`
stubs at the bottom of `vdi.py` — delete those; file bytes must never travel
through a tool result.)

- Tool `get_revision_file(vdi_id, revision_id, side)` where `side` is
  `"submit"` or `"return"`:
  1. Fetch the revision via `get_api(f"vdi/{vdi_id}/revisions/{revision_id}")`,
     friendly 404 if missing; friendly message if the requested side has no file
     (e.g. no return yet).
  2. Extract the `file.id` from the chosen side of the `RevisionRead` payload.
  3. Mint `PendingTransfer(kind="download", pat=..., file_id=...)` and return:
     `curl -o "<filename>" "{MCP_PUBLIC_URL}/downloads/{token}"`, using the
     original filename from the payload.
- Route `GET /downloads/{token}`: consume the token (kind-checked), fetch
  `GET /api/files/{file_id}?download=1` from Onyx with the stored PAT, and relay
  the bytes with the original filename and content type. Stream
  (`httpx` streaming response → `StreamingResponse`) rather than buffering, since
  return documents can be as large as submittals.
- Same 404-for-unknown-or-expired behavior as uploads.

## Phase 5 — the buyer's return side (stage/finalize)

Recording a return is the most consequential write in the system — the buyer's
decision, changing the VDI's status (A/D approve, B/C reject). It therefore uses
the same stage/finalize confirmation ceremony as project updates (`stage_project_update`
/ `finalize_project_update`), guarding against a confused agent firing it casually.

- **`stage_vdi_return(vdi_id, return_code, filename, comments=None)`**:
  validates the VDI exists and is in a returnable status, stores
  `{vdi_id, return_code, filename, comments}` under a stage key (same in-memory
  dict pattern as `staged_projects`), and returns a summary the agent must show
  the user for approval — e.g. "Returning <VDI name> with code B (rejected),
  document <filename>, comments: ... — confirm?". `return_code` is a `StrEnum`
  (A/B/C/D) mirroring `SubmitCode`. The stage key is never shown to the user.
- **`finalize_vdi_return(stage_key)`**: consumes the staged return and mints a
  `PendingTransfer(kind="upload", purpose="return", ...)` carrying the return
  fields, returning the one-time upload URL + curl instructions as in Phase 2.
  The Onyx call happens when the bytes arrive: the upload route branches on
  `purpose` — `"submit"` → `POST vdi/{id}/submit`; `"return"` →
  `POST vdi/{id}/return` with `form_fields={"return_code": ..., "comments": ...}`
  (`post_file_api` already accepts `form_fields`).
- Same status guard story throughout: Onyx 409s if the VDI is not in a returnable
  status, and the stage tool pre-checks so the user hears about it before
  approving anything.
- `PendingTransfer` grows `purpose: Literal["submit", "return"]` plus
  `return_code`/`comments` fields (used only when `purpose == "return"`).

---

## Hardening checklist (before real users touch the hosted deployment)

- [ ] HTTPS only, for both the MCP server and Onyx (PATs and documents in transit).
- [ ] Confirm nothing logs Authorization headers, tokens, or request bodies
      (server access logs included — the upload token is in the URL path, so keep
      access-log retention short or mask the path).
- [ ] Reverse-proxy body-size limit aligned with `MAX_UPLOAD_BYTES` (e.g. nginx
      `client_max_body_size`), so oversized uploads die at the edge.
- [ ] Rate-limit `PUT /uploads/*` (cheap protection against URL guessing, even
      though 256-bit tokens make it moot in practice).
- [ ] Decide `UPLOAD_TTL_SECONDS` and `MAX_UPLOAD_BYTES` for real usage
      (10 min / 100 MB are reasonable starting points for construction PDFs).
- [ ] A restart drops pending uploads — acceptable, but make the 404 message tell
      the user to just start the submission again (it already does).

## Suggested commit sequence

1. `post_file_api` multipart helper in `onyx.py`.
2. `transfers.py` pending-transfer store with tests for single-use, expiry, and
   kind-checking (also delete the two `-> bytes` stubs in `vdi.py`).
3. Upload route + `submit_vdi` tool (Phase 2) + manual test.
4. Download route + `get_revision_file` tool (Phase 4) + manual test.
5. `stage_vdi_return` / `finalize_vdi_return` (Phase 5).
