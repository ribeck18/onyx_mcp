# onyx-web (MCP)

An MCP server that exposes Onyx construction-project data as tools for an AI assistant.
It authenticates to Onyx's HTTP API on behalf of the signed-in user with a per-user
Personal Access Token.

## Language

**Onyx**:
The deployed construction-project web application and its HTTP API, reached over HTTPS.
The MCP is a client of Onyx; Onyx is the source of truth for projects.
_Avoid_: the main app, the backend, the server

**MCP**:
This project — a hosted, multi-user MCP server (HTTP transport) that exposes Onyx data
as assistant tools. One deployment serves many users; each request authenticates with
that user's PAT. Running it on localhost is a dev convenience, not the deployment model.
_Avoid_: the tool server, the connector

**PAT (Personal Access Token)**:
An Onyx-issued, per-user bearer credential that the MCP sends to Onyx as
`Authorization: Bearer <PAT>`. Minted by the user in the Onyx app; expires after 90 days.
_Avoid_: API key, access token, secret

**VDI (Vendor Data Item)**:
A single piece of required vendor documentation that belongs to a Project. Tracks its
own lifecycle status from `NOT_STARTED` through approval. Has many Revisions.
_Avoid_: document, submittal item, line item

**Revision**:
One round-trip with the buyer on a VDI — a submittal sent out and (optionally) a
return received back. All history lives in Revisions; the VDI status always reflects
the current state. A Revision always represents a real submittal; it is never a
draft. Revision numbers are assigned by Onyx, never chosen by the user.
_Avoid_: version, draft, attempt

**Submittal**:
The document sent to the buyer when a VDI is submitted; opening move of a Revision.
The buyer's answer is the **return** (a return code A–D, a returned document, and
optional comments) — returning closes the Revision's round-trip.
_Avoid_: upload, attachment, file (when the domain act is meant)

**Setup CLI**:
A command users run once to paste their PAT; it validates the token against Onyx and
registers the hosted MCP's URL (with the PAT as the connection's bearer credential)
with the user's AI client.
_Avoid_: installer, configurator
