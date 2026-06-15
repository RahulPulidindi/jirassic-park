"""FastMCP server registration.

Provides `build_mcp()` and `mount_mcp(app, mcp)` to attach a Streamable-HTTP
MCP server at /mcp exposing `jira_*` tools that wrap the same service layer
the REST API uses.

This is the agent-facing surface. Tool docstrings include pitfalls and examples
so agents have what they need to self-correct without UI screenshots.

NOTE: the FastMCP streamable-HTTP app requires its session_manager to be
running inside an async context. We do that from a FastAPI lifespan in
app.main rather than at mount time.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def build_mcp():
    """Construct (but do not run) the FastMCP server with all jira_* tools."""
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings

    from app.mcp.tools import register_tools

    # Relax DNS rebinding / origin checks: this env is meant for local agents
    # and reviewers, possibly running inside Docker (hostnames are not
    # localhost). Not for production deployments.
    loose = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
        allowed_hosts=["*"],
        allowed_origins=["*"],
    )
    mcp = FastMCP(
        "jirassic-park",
        instructions=(
            "Jirassic Park is a Jira-like project tracker. Use jira_* tools "
            "to read and mutate issues, sprints, boards, and projects. Most "
            "mutating tools require Authorization: Bearer <api_token>; pass "
            "it as a header on tool calls."
        ),
        # The streamable-HTTP sub-app is mounted by FastAPI at /mcp, so we
        # want the inner route to be /  (otherwise the public path becomes
        # /mcp/mcp).
        streamable_http_path="/",
        transport_security=loose,
    )
    register_tools(mcp)
    return mcp


def mount_mcp(app: FastAPI, mcp) -> None:
    """Mount the MCP streamable-HTTP sub-app onto the FastAPI app at /mcp."""
    app.mount("/mcp", mcp.streamable_http_app())
    logger.info("MCP server mounted at /mcp")


@asynccontextmanager
async def mcp_lifespan(mcp):
    """Async context that starts/stops the FastMCP session manager."""
    async with mcp.session_manager.run():
        yield
