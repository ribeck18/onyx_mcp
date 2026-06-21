import json

import httpx
from mcp.server.fastmcp import FastMCP

from onyx import get_api, post_api, patch_api


async def list_all_projects() -> str:
    """Gets a complete list of all the exisiting projects.

    Use this when you need a list of all projects.
    The project id is its primary key used in the data base and is not commonly used by a user. A user will typically mention a project_number or a project name, not the id.
    """
    try:
        result = await get_api("projects")
    except httpx.HTTPStatusError as err:
        if err.response.status_code == 404:
            return "The projects endpoint could not be found (check the path)."
        raise
    except httpx.RequestError as err:
        return f"Could not reach the onyx_web server: {err}"

    projects = []
    for proj in result:
        project = {
            "id": proj.get("id"),
            "name": proj.get("name"),
            "project_number": proj.get("project_number"),
        }
        projects.append(project)

    return json.dumps(projects, indent=4)


async def get_single_project(project_id: int) -> str:
    """
    Gets a single project from the database. Use this when you need to retrieve a project, project_id is a primary key from the database Usually users will not know the primary key and will mention a project name or project_number. Use list_all_projects to match an id to a project the user mentions.
    """
    try:
        result = await get_api("projects")
    except httpx.HTTPStatusError as err:
        if err.response.status_code == 404:
            return f"Project with id {project_id} could not be found."
        raise
    except httpx.RequestError as err:
        return f"Could not reach the onyx_web server: {err}"

    return json.dumps(result, indent=4)


async def create_project(
    project_number: str, project_name: str, project_description: str | None = None
) -> str:
    """Creates a new project.
    Use this when a user says that they want to create a new project.
    The project_number should only be entered explicitly as the user says it.
    Make sure to explicitly ask the user for the project number if they have not already provided it.
    A description is a short summary of the scope of a project.
    """
    payload = {
        "project_number": project_number,
        "name": project_name,
        "description": project_description,
    }

    result = await post_api(path="projects", payload=payload)

    return json.dumps(result, indent=4)


async def update_existing_project(
    project_id: int,
    project_number: str | None = None,
    project_name: str | None = None,
    project_description: str | None = None,
) -> str:
    """Make updates to an exisiting project.
    Only make updates to fields that the user has explicitly asked you to update.
    """
    payload = {}
    if project_number is not None:
        payload["project_number"] = project_number
    if project_name is not None:
        payload["name"] = project_name
    if project_description is not None:
        payload["description"] = project_description

    try:
        result = await patch_api(path=f"projects/{project_id}", payload=payload)

    except httpx.HTTPStatusError as err:
        if err.response.status_code == 404:
            return f"No project with id {project_id} could be found."
        raise
    except httpx.RequestError as err:
        return f"Could not reach the onyx_web server: {err}"

    return f"The project has been updated, and is now: {json.dumps(result, indent=4)}"
