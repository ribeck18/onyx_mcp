"""MCP-boundary tests for the project read tools: tool calls go through an
in-process MCP client session, Onyx mocked at the outbound httpx layer."""

import json

import pytest

import projects
from conftest import mcp_session


pytestmark = pytest.mark.anyio

PROJECT_42 = {
    "id": 42,
    "name": "Harbor Bridge Retrofit",
    "project_number": "P-1042",
    "description": "Seismic retrofit of the harbor bridge.",
}


def tool_text(result) -> str:
    return "".join(block.text for block in result.content if block.type == "text")


async def call_get_single_project(app, project_id):
    async with mcp_session(app) as session:
        result = await session.call_tool(
            "get_single_project", {"project_id": project_id}
        )
    return tool_text(result)


async def test_get_single_project_fetches_by_id(app, onyx_mock):
    route = onyx_mock.get("/api/projects/42").respond(200, json=PROJECT_42)

    text = await call_get_single_project(app, 42)

    assert route.called
    payload = json.loads(text)
    assert isinstance(payload, dict)  # exactly one project, not a list
    assert payload == PROJECT_42


async def test_get_single_project_unknown_id(app, onyx_mock):
    onyx_mock.get("/api/projects/999").respond(
        404, json={"detail": "Project not found"}
    )

    text = await call_get_single_project(app, 999)

    assert "Project with id 999 could not be found." in text


async def test_finalize_project_update_unknown_stage_key():
    projects.staged_projects.clear()

    text = await projects.finalize_project_update("missing")

    assert "No staged project is associated with missing" in text


async def test_finalize_project_update_consumes_stage_key(monkeypatch):
    projects.staged_projects.clear()
    projects.staged_projects["stage-1"] = {"id": 42, "name": "New Name"}
    calls = []

    async def fake_patch_api(path, payload):
        calls.append((path, payload))
        return {"id": 42, "name": "New Name"}

    monkeypatch.setattr(projects, "patch_api", fake_patch_api)

    text = await projects.finalize_project_update("stage-1")
    replay = await projects.finalize_project_update("stage-1")

    assert calls == [("projects/42", {"id": 42, "name": "New Name"})]
    assert "The project has been updated" in text
    assert "No staged project is associated with stage-1" in replay
