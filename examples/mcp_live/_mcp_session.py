"""Shared MCP session setup for the mcp_live examples.

Provides a reusable async context manager that:
  - Creates a temporary directory (isolated workspace)
  - Launches @modelcontextprotocol/server-filesystem via npx
  - Initializes the MCP ClientSession
  - Tears everything down on exit

Usage in any example:
    async with mcp_session() as (session, workdir):
        toolkit = await Toolkit.from_mcp(session)
        ...

Requirements:
    - Node.js / npx on PATH
    - pip install "ez-ptc[mcp]"
"""

from __future__ import annotations

import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@asynccontextmanager
async def mcp_session(extra_dirs: list[str] | None = None):
    """Yield an initialized MCP ClientSession backed by a real filesystem server.

    Creates a fresh temp directory as the server root so examples run in
    an isolated, throwaway location.

    Args:
        extra_dirs: Additional absolute paths to allow the server to access.

    Yields:
        (session, workdir): An initialized ClientSession and a Path to the
                            temporary working directory.
    """
    with tempfile.TemporaryDirectory(prefix="ez_ptc_mcp_") as tmpdir:
        # Resolve symlinks so the path matches what the MCP server sees.
        # (On macOS, /var/folders is a symlink to /private/var/folders.)
        workdir = Path(tmpdir).resolve()
        allowed = [str(workdir)] + (extra_dirs or [])

        server = StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem"] + allowed,
        )

        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session, workdir
