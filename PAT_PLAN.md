# PAT Auth Cutover Plan

Goal: when Onyx's API closes to anonymous traffic, the MCP must authenticate to it
with a **per-user Personal Access Token (PAT)**, sending `Authorization: Bearer <PAT>`
on every API call, and surface a clear failure when the token is missing, expired, or
revoked (the API returns **401** in those cases).

Deployment model: **shared server** (one MCP process serving many users), confirmed.

---

## Key constraints this forces

A shared server has no per-user process, so there is no per-user environment variable.
The PAT must arrive **on each request** and the server picks it off the wire. Two
consequences, both verified against the installed SDK (`mcp 1.28.0`):

1. **Transport must be HTTP, not stdio.** Today `main.py` calls `mcp.run()`, which
   defaults to **stdio** — no per-request headers. A shared multi-user server must run
   over `streamable-http`. The request plumbing exists: inside a tool,
   `mcp.get_context().request_context.request` is the raw Starlette request, so
   `.headers.get("authorization")` yields the caller's token per-request.
   (`RequestContext` has a `request` field; confirmed.)

2. **Design is PAT pass-through.** The main app (the MCP *client*) already knows the
   user via Entra SSO. It looks up that user's Onyx PAT and sends it as
   `Authorization: Bearer <PAT>` on the MCP HTTP call. The MCP reads that header and
   forwards it to the Onyx API. The MCP stays stateless about identity — it is a typed
   proxy in front of Onyx's own API, which is exactly the case where forwarding a bearer
   token is appropriate (the PAT is an Onyx credential destined for Onyx).

   The SDK's full OAuth path (`TokenVerifier` + `get_access_token()`) was considered and
   rejected: it is built to *verify* a token, whereas Onyx's API wants the PAT
   *forwarded*. Verifying the Entra token would not produce a PAT. Pass-through is
   simpler and matches the requirement literally.

---

## The plan, file by file

### 1. `main.py` — switch transport to HTTP
- Run `mcp.run(transport="streamable-http")` with host/port (the SDK serves it via an
  ASGI app under uvicorn).
- This is the deployment change: the MCP becomes a long-running HTTP service, fronted by
  TLS, not a stdio subprocess.

### 2. `onyx.py` — read the per-request PAT and attach the header (core change)
- Add a helper, e.g. `_user_token()`, that pulls the bearer token from
  `mcp.get_context().request_context.request.headers["authorization"]`. If the header is
  absent or malformed, raise a clear "no token supplied" error — **never fall back to
  anonymous**.
- In all three helpers (`get_api`, `post_api`, `patch_api`), set
  `headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}`. This also
  finally uses the `USER_AGENT` constant that is currently dead. Fixing it in this one
  shared layer covers every tool.
- Keep the fixed `ONYX_URL` target so a forwarded token can only ever go to Onyx, never
  an arbitrary host.

### 3. Centralized 401 handling (the "clear failure" requirement)
- Today only **404** is caught, and only in some tools — `create_project` catches
  nothing, so a 401 there is an unhandled crash. Add 401 handling in **one** place so all
  four tools behave the same.
- Cleanest approach: catch `httpx.HTTPStatusError` in the API helpers, and on
  `status_code == 401` raise a dedicated `AuthError` with a user-facing message such as:
  *"Authentication to Onyx failed (401): your Personal Access Token is missing, expired,
  or revoked. Generate a new token and reconnect."* Wrap each tool (a small decorator or
  shared try/except) to turn `AuthError` into that string. This also folds in the
  missing-token case from step 2.
- 401 must be distinguished from 403/404 — the requirement is specifically that 401 =
  bad/absent token.

### 4. Token hygiene
- Do not log or echo the token; keep it out of error strings and logs.

---

## Out of scope but flagged
- `vdi.py` is broken WIP (a half-written `get_all_vendor_data_for_project` with a
  dangling `try`, no `@mcp.tool`) and is not imported by `main.py`, so it will not affect
  the cutover — but it must not be wired in as-is.

---

## External dependency (cannot be satisfied from inside this repo)
This design assumes **the main app can attach the signed-in user's Onyx PAT as the
`Authorization` header on its MCP requests.** That requires, on the Onyx/main-app side:
1. users can mint a PAT,
2. those PATs are stored server-side keyed to the Entra identity, and
3. the MCP client is configured to send them.

If the main app can only forward the *Entra* token to the MCP, the design changes
materially (the MCP would need to exchange Entra → PAT). Confirm this pass-through
assumption before implementation.
