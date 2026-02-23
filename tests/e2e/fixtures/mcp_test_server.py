#!/usr/bin/env python3
"""Minimal MCP server for pitlane E2E tests.

Exposes a single tool `write_marker` that writes a deterministic
marker file, allowing validation via file_exists + file_contains.
The marker content is unique enough to prove the MCP tool was used.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pitlane-test")

MARKER_CONTENT = "PITLANE_MCP_MARKER_a9f3e7b2"


@mcp.tool()
def write_marker() -> str:
    """Write a marker file called .mcp_marker to the current directory.
    IMPORTANT: You MUST call this tool. It writes a verification file."""
    import os

    path = os.path.join(os.getcwd(), ".mcp_marker")
    with open(path, "w") as f:
        f.write(MARKER_CONTENT)
    return f"Marker written to .mcp_marker with content: {MARKER_CONTENT}"


if __name__ == "__main__":
    mcp.run()
