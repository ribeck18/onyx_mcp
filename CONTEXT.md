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
This project — the stdio MCP server that runs locally on a user's machine and exposes
Onyx data as assistant tools.
_Avoid_: the tool server, the connector

**PAT (Personal Access Token)**:
An Onyx-issued, per-user bearer credential that the MCP sends to Onyx as
`Authorization: Bearer <PAT>`. Minted by the user in the Onyx app; expires after 90 days.
_Avoid_: API key, access token, secret

**Setup CLI**:
A command users run once to paste their PAT; it validates the token against Onyx, writes
it to a local credentials file, and registers the MCP with the user's AI client.
_Avoid_: installer, configurator
