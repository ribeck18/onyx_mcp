import json
import time

import httpx
import enum

from config import mcp_public_url
from onyx import AuthError, get_api, post_api, patch_api, mcp, _user_token
from transfers import PendingTransfer, TRANSFER_TTL_SECONDS, create_transfer


SUBMITTABLE_STATUSES = {"not_started", "b", "c"}


##Enums - approval code, submit code
class SubmitCode(enum.StrEnum):
    """When a submittal is due relative to the project timeline."""

    AC = "ac"  # As Completed
    AFI = "afi"  # At Final Inspection
    ARO = "aro"  # After Receipt of Order
    AT = "at"  # After Test
    BC = "bc"  # Before Contract Awarded
    BFA = "bfa"  # Before Final Acceptance
    BFS = "bfs"  # Before Fabrication Start
    PDS = "pds"  # Prior to Delivery on Site
    PS = "ps"  # Prior to Shipment
    PT = "pt"  # Prior to Test
    PTC = "ptc"  # Prior to Construction
    PTI = "pti"  # Prior to Installation
    PTP = "ptp"  # Prior to Purchase
    PTW = "ptw"  # Prior to Welding
    ROS = "ros"  # Prior to Removal Off-Site
    TS = "ts"  # Time of Shipment


class ApprovalType(enum.StrEnum):
    """Whether a vendor data item requires buyer approval or is informational only."""

    MANDATORY_APPROVAL = "mandatory_approval"
    INFORMATION_ONLY = "information_only"


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


@mcp.tool()
async def create_new_vendor_data_item(
    project_id: int,
    item_number: int,
    name: str,
    approval_type: ApprovalType,
    submit_code: SubmitCode,
    submittal_number: str | None = None,
    description: str | None = None,
    spec_drawing_reference: str | None = None,
    notes: str | None = None,
) -> str:
    """Creates a new vendor data item for a project. Use this tool whenever a user wants to add vendor data to a project.

    approval_type is an enum with the following values:
    "mandatory_approval"
    "information_only"

    submit_code is also an enum with the following values:
    "ac"  # As Completed
    "afi"  # At Final Inspection
    "aro"  # After Receipt of Order
    "at"  # After Test
    "bc"  # Before Contract Awarded
    "bfa"  # Before Final Acceptance
    "bfs"  # Before Fabrication Start
    "pds"  # Prior to Delivery on Site
    "ps"  # Prior to Shipment
    "pt"  # Prior to Test
    "ptc"  # Prior to Construction
    "pti"  # Prior to Installation
    "ptp"  # Prior to Purchase
    "ptw"  # Prior to Welding
    "ros"  # Prior to Removal Off-Site
    "ts"  # Time of Shipment

    project_id is a primary key for the database and the user will not know it. They will refer to projects by name or project_number. Never reveal the primary_key (id) of projects or vendor data to the user.
    """

    try:
        payload = {
            "project_id": project_id,
            "item_number": item_number,
            "name": name,
            "approval_type": approval_type,
            "submit_code": submit_code,
            "submittal_number": submittal_number,
            "description": description,
            "spec_drawing_reference": spec_drawing_reference,
            "notes": notes,
        }

        new_vdi = await post_api("vdi", payload=payload)
    except AuthError as err:
        return str(err)
    except httpx.RequestError as err:
        return f"Could not reach the onyx_web server: {err}"
    except httpx.HTTPStatusError as err:
        if err.response.status_code == 404:
            return f"Project with id {project_id} could not be found."
        raise

    return json.dumps(new_vdi, indent=4)


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

    status = vdi.get("status")
    if status not in SUBMITTABLE_STATUSES:
        return (
            f"This vendor data item cannot be submitted from its current "
            f"status ({status}). A submittal is only possible when the item "
            f"is not started or its last return was code B or C."
        )

    token = create_transfer(
        PendingTransfer(
            kind="upload",
            pat=_user_token(),
            expires_at=time.time() + TRANSFER_TTL_SECONDS,
            purpose="submit",
            vdi_id=vdi_id,
            filename=filename,
        )
    )

    return (
        "Upload link created (expires in 10 minutes, single use).\n"
        "\n"
        "BEFORE uploading: tell the user which file you are submitting and to "
        "which vendor data item, and wait for their confirmation. A submittal "
        "is permanent revision history.\n"
        "\n"
        "Then run this on the machine that has the file (not in a remote "
        "sandbox):\n"
        "\n"
        f'    curl -sS -T "<local path to file>" "{mcp_public_url}/uploads/{token}"\n'
        "\n"
        "On Windows/PowerShell use `curl.exe` (plain `curl` is an alias for "
        "Invoke-WebRequest and takes different flags).\n"
        "\n"
        "The response will confirm the revision was opened. Verify with "
        "get_revisions_for_vdi if needed. If the link has expired, simply "
        "start over by calling submit_vdi again."
    )
