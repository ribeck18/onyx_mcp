# File bytes cross the MCP boundary only via single-use transfer URLs

The MCP is a hosted, multi-user server; the documents (almost always PDFs, 1–50 MB)
live on users' machines. We decided that file bytes never travel through the MCP
protocol itself: a tool call mints a short-lived (10 min), single-use, unguessable
URL on the MCP server, and the user's agent moves the bytes with a plain HTTP
request to that URL (`curl -T` up, `curl -o` down). The server captures the PAT
during the tool call and uses it to forward to / fetch from Onyx; the PAT never
leaves the server, and the token URL — worthless after one use — is the only thing
the agent ever sees.

## Considered options

- **Base64 through tool arguments/results** — rejected: construction PDFs blow past
  message limits and would cost enormous token counts.
- **Agent calls Onyx directly with the PAT** — rejected: the PAT (scoped to
  everything the user can do) would leak into agent context and shell history.
- **Tool accepts a server-side `file_path`** — rejected: on a multi-user host this
  is an arbitrary-file-read exfiltration channel (submit `/home/onyx/.env` to Onyx,
  download it back). Not even offered as a dev-only mode.
- **Tool accepts a `file_url` the server fetches** — rejected: the useful links
  (SharePoint, vendor portals) are authenticated and only fetchable from the user's
  machine anyway, and server-side fetching is an SSRF vector against Onyx, which
  shares the VPS.

## Consequences

- Upload/download tools return *instructions for the agent*, not results; the
  transfer completes out-of-band and agents verify via a follow-up read tool.
- The pending-transfer store is an in-memory dict, which constrains the MCP to a
  **single process forever** (one uvicorn worker, vertical scaling only — fine at
  ≤4 users). Horizontal scaling would require moving the store to Redis behind the
  existing `create_transfer`/`consume_transfer` seam.
- A server restart silently drops pending transfers; the 404 message tells the
  caller to start over.
- Transfer tokens ride in URL paths, so access logs must be treated as
  secret-bearing (short retention or path masking).
