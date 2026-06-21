import json

import httpx
from mcp.server.fastmcp import FastMCP

from onyx import get_api, post_api


async def get_all_vendor_data_for_project() -> str:
    """"""
    try:
        result = get_api()


async def get_vendor_data_item() -> str:
    pass


async def get_revisions_for_vdi() -> str:
    pass


async def get_submit_file_from_revision() -> bytes:
    pass


async def get_return_file_from_revison() -> bytes:
    pass
