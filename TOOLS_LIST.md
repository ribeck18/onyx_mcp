# Onyx MCP — Tools List

This document tracks the tools currently exposed by the Onyx MCP server and the
candidate tools we could add by wrapping the remaining `onyx_web` HTTP routes.

- **MCP repo:** `ribeck18/onyx_mcp` (this working directory)
- **Backend (Onyx) repo:** `ribeck18/onyx_web` — the FastAPI app the MCP calls
- All backend routes are mounted under `/api` and require a per-user PAT
  (`Authorization: Bearer <PAT>`).

---

## 1. Tools already in the MCP

Defined in `projects.py` (registered via `@mcp.tool()`):

| Tool | Backend call | Purpose |
|------|--------------|---------|
| `list_all_projects` | `GET /api/projects` | List all projects (id, name, project_number). |
| `get_single_project` | `GET /api/projects` | Fetch a single project. *(Note: currently lists all projects and ignores `project_id` — a bug to revisit.)* |
| `create_project` | `POST /api/projects` | Create a new project. |
| `stage_project_update` | *(local staging only)* | Stage a project patch and return a `stage_key` for confirmation. |
| `finalize_project_update` | `PATCH /api/projects/{id}` | Apply a staged project update after user approval. |

Coverage so far: **Projects only** (missing DELETE), using the stage/finalize
confirmation pattern for mutations.

---

## 2. Backend routers in `onyx_web`

| Router file | Prefix | Auth |
|-------------|--------|------|
| `app/project/router.py` | `/projects` | authenticated user |
| `app/vdi/router.py` | `/vdi` | authenticated user |
| `app/vdi/revision/router.py` | `/vdi/{vdi_id}/revisions` | authenticated user |
| `app/file/router.py` | `/files` | authenticated user |
| `app/auth/router.py` | `/users` | **admin only** (`current_admin`) |
| `app/auth/token_router.py` | `/tokens` | authenticated user |

---

## 3. Candidate tools to add

### Projects (`/projects`) — partially covered
| Candidate tool | Route | Notes |
|----------------|-------|-------|
| `delete_project` | `DELETE /projects/{id}` | Deletes project + all its VDIs and Revisions. Destructive — use the stage/finalize confirmation pattern. |
| *(fix)* `get_single_project` | `GET /projects/{id}` | Repoint the existing tool at the by-id route instead of listing all. |

### VDI — Vendor Data Items (`/vdi`) — **not covered, highest value**
| Candidate tool | Route | Notes |
|----------------|-------|-------|
| `create_vdi` | `POST /vdi` | Create a VDI under a project. 409 if item_number already used. |
| `list_vdis` | `GET /vdi?project_id=` | List VDIs in a project (project_id required). |
| `get_vdi` | `GET /vdi/{vdi_id}` | Fetch a single VDI. |
| `update_vdi` | `PATCH /vdi/{vdi_id}` | Patch editable fields; submission fields lock after submit. |
| `submit_vdi` | `POST /vdi/{vdi_id}/submit` | Multipart file upload; opens next Revision. Needs file-upload handling. |
| `return_vdi` | `POST /vdi/{vdi_id}/return` | Multipart: return_code (A/B/C/D), file, comments. |
| `delete_vdi` | `DELETE /vdi/{vdi_id}` | Deletes VDI + cascaded Revisions. Destructive — confirm first. |

### Revisions (`/vdi/{vdi_id}/revisions`) — read-only history
| Candidate tool | Route | Notes |
|----------------|-------|-------|
| `list_revisions` | `GET /vdi/{vdi_id}/revisions` | Full revision history for a VDI. |
| `get_latest_revision` | `GET /vdi/{vdi_id}/revisions/latest` | Most recent revision. |
| `get_revision` | `GET /vdi/{vdi_id}/revisions/{revision_id}` | A single revision. |

### Files (`/files`)
| Candidate tool | Route | Notes |
|----------------|-------|-------|
| `download_file` | `GET /files/{file_id}` | Returns raw bytes. Binary response — decide how to surface (link, path, or base64) in an MCP context. |

---

## 4. Suggested priority

1. **VDI CRUD** (`create/list/get/update/delete_vdi`) — the core domain object,
   entirely unexposed today.
2. **Revisions** (read-only) — cheap, high-value context for the assistant.
3. **`delete_project`** + fix `get_single_project` — close the Projects gap.
4. **`submit_vdi` / `return_vdi`** — powerful but need multipart file-upload
   plumbing the MCP doesn't have yet.
5. **Tokens / Users / Files** — lower priority; admin and credential surfaces
   that may be better left out of the assistant, or added last with care.
