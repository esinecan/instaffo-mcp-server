"""FastMCP server. Registers only what actually works today: auth status.

The candidate-side domain tools are intentionally absent until the API fork is
decided (see instaffo_mcp/tools/surface.py and the README).
"""

from __future__ import annotations

from fastmcp import FastMCP

from instaffo_mcp import __version__
from instaffo_mcp.tools.auth import register_auth_tools
from instaffo_mcp.tools.profile_writes import register_profile_write_tools
from instaffo_mcp.tools.reads import register_read_tools
from instaffo_mcp.tools.writes import register_write_tools


def create_mcp_server() -> FastMCP:
    mcp = FastMCP("instaffo-mcp-server", version=__version__)
    register_auth_tools(mcp)
    register_read_tools(mcp)
    register_write_tools(mcp)
    register_profile_write_tools(mcp)
    return mcp
