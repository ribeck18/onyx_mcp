import json

import httpx

from onyx import AuthError, get_api, post_api, patch_api, mcp


@mcp.tool()
async def get_all_vendor_data_for_project(project_id: int) -> str:
    """Gets all of the vendor data items, no matter their current status, from a specific project. Use this tool when a user wants to know what vendor data is associatd with a project. project_id is a primary key from the database Usually users will not know the primary key and will mention a project name or project_number. Do not tell the project_id to the user. This tool will include in its return an item number and a submittal number, these are different. Item number is often assigned by the buyer. While the submittal number is often defined by the user. It is possible for the submittal number to be empty, that is okay."""
    try:
        result = await get_api(f"vdi?project_id={project_id}")
    except AuthError as err:
        return str(err)
    except httpx.HTTPStatusError as err:
        if err.response.status_code == 404:
            return f"Project with id {project_id} could not be found."
        raise
    except httpx.RequestError as err:
        return f"Could not reach the onyx_web server: {err}"

    vdis = []
    for vdi in result:
        item = {
            "id": vdi.get("id"),
            "name": vdi.get("name"),
            "item_number": vdi.get("item_number"),
            "submittal_number": vdi.get("submittal_number"),
            "status": vdi.get("status"),
            "updated_at": vdi.get("updated_at"),
        }
        vdis.append(item)
    return json.dumps(vdis, indent=4)


@mcp.tool()
async def get_vendor_data_item(vdi_id: int) -> str:
    """Gets a specific vendor data item, and all the information associatd with it. Use this tool when a user wants details on a specific vendor data item. The vdi_id is an internal primary key and the user will not know it, they will typically refer to vendor data items by name. You should never reveal the primary_key id to the user."""
    try:
        vdi = await get_api(f"vdi/{vdi_id}")
    except AuthError as err:
        return str(err)
    except httpx.HTTPStatusError as err:
        if err.response.status_code == 404:
            return f"Vendor data item with id {vdi_id} could not be found."
        raise
    except httpx.RequestError as err:
        return f"Could not reach the onyx_web server: {err}"

    return json.dumps(vdi, indent=4)


@mcp.tool()
async def get_revisions_for_vdi(vdi_id: int) -> str:
    """Gets all of the revisions for a specific vendor data item. A vendor data item is complete when it's most recent revision is marked as approved. Do not reveal to the user the primary key of any revision or vendor data item."""
    try:
        revisions = await get_api(f"vdi/{vdi_id}/revisions")
    except AuthError as err:
        return str(err)
    except httpx.HTTPStatusError as err:
        if err.response.status_code == 404:
            return f"Vendor data item with id {vdi_id} could not be found."
        raise
    except httpx.RequestError as err:
        return f"Could not reach the onyx_web server: {err}"

    return json.dumps(revisions, indent=4)


async def get_submit_file_from_revision() -> bytes:
    pass


async def get_return_file_from_revison() -> bytes:
    pass
