# Onyx MCP

This connects AI assistants to [Onyx](https://github.com/ribeck18/onyx_web), my construction-project web app. Once connected, you can ask your assistant about your projects and vendor data items in plain English — things like "what's the status of the VDIs on the Riverside project?" or "create a new project for the Oakdale build" — and it will look up or update the real data in Onyx for you.

## Who it's for

Anyone on your team who works in Onyx and wants to get things done through an AI assistant instead of clicking through the app. 

## How to use it

In order to use **Onyx MCP** You first need to setup **Onyx Web** which you can find [here](https://github.com/ribeck18/onyx_web) it is also intended that you run this MCP on a server (likely the same one you run Onyx Web on.)

1. **Get a Personal Access Token (PAT) from Onyx.** This is how the server knows who you are — the assistant can only see and do what your Onyx account allows.
2. **Add the server to your AI assistant** using the server's URL, with your PAT as the bearer token. 
3. **Start asking.** Some things you can do:
   - Look up a project or list all projects
   - Create a new project
   - Update a project — the assistant will show you the changes and ask you to confirm before applying them
   - Browse a project's vendor data items (VDIs), see full details and revision history
   - Create a new VDI

If your token expires or gets revoked, you'll get a clear message telling you to generate a new one in Onyx and reconnect.

## Import note for server setup

Requires Python 3.12+. Put the Onyx URL, user-agent, and the MCP's public base URL in a `.env` file, then start it with `uv run main.py`:

```
ONYX_URL=https://your-onyx-host
USER_AGENT=onyx-app/1.0
MCP_PUBLIC_URL=https://your-mcp-host   # externally reachable base URL of this MCP; used to build one-time upload links (http://localhost:8000 for local dev)
```

It serves all users from one process — each request carries the user's own token, so the server holds no credentials itself.

**Run exactly one process (one uvicorn worker).** Pending file transfers (the one-time upload links used to submit documents) live in in-memory state, so the server must never be scaled to multiple workers or replicas. `uv run main.py` already does the right thing. If the server restarts, any pending upload links are dropped — just ask the assistant to start the submission again.
