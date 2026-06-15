"""Test fixtures.

We isolate test runs from the host's `/data` by setting DATA_DIR to a per-session
temp directory, then we run the seed builder once per session. Each test gets
its own session-scoped DB but with a fresh state (state.db copied from seed.db).
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Make app importable when pytest is run from the repo root
_BACKEND = Path(__file__).parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(scope="session", autouse=True)
def _data_dir():
    tmp = tempfile.mkdtemp(prefix="jp_test_")
    # Settings reads DATA_DIR via the JP_ prefix because of env_prefix="JP_".
    # We also set the bare DATA_DIR for any code that reads os.environ directly.
    os.environ["DATA_DIR"] = tmp
    os.environ["JP_DATA_DIR"] = tmp
    # Pin the universal clock so timestamp-derived ids (comment_xxx_<ts>,
    # link_..._<ts>) collide identically across REST/MCP parity runs and so
    # seeded "X days ago" reads as a stable instant. `tick:` advances by 1us
    # per call so two activities in the same operation get strictly increasing
    # timestamps (required for stable order-by in the parity tests).
    os.environ["JP_CLOCK"] = "tick:2026-05-27T12:00:00Z"
    # Clear lru_cache so the new env var is picked up
    from app.config import settings as _settings
    _settings.cache_clear()
    from app import clock as _clock
    _clock.configure_from_env()

    # Build seed once
    from app.seed.builder import rebuild

    rebuild()
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_state():
    """Restore state.db from seed.db before every test and re-anchor the clock."""
    from app import clock as _clock
    from app.db import dispose_engine, init_engine, reset_state_from_seed

    reset_state_from_seed()
    init_engine()
    # The seed builder consumed some ticks; rewind to a known anchor so each
    # test sees the same starting "now" and parity runs line up.
    _clock.tick_from("2026-05-27T12:00:00Z")
    yield
    dispose_engine()


@pytest.fixture()
def db():
    from app.db import session_scope

    with session_scope() as s:
        yield s


@pytest.fixture()
def client():
    """REST client (FastAPI TestClient)."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def mcp_call():
    """Async helper that calls an MCP tool by name with a given args dict."""
    import asyncio
    import json as _json

    from mcp.server.fastmcp import FastMCP

    from app.mcp.tools import register_tools

    mcp = FastMCP("jirassic-park-test")
    register_tools(mcp)  # both jira_* and Atlassian-named aliases

    def _call(name: str, args: dict):
        async def _go():
            return await mcp.call_tool(name, args)

        result = asyncio.get_event_loop().run_until_complete(_go())
        # FastMCP's call_tool returns one of:
        #   - list[TextContent]                 (single-value tool, parse [0].text)
        #   - tuple(list[TextContent], structured)  (collection tool: each list item
        #                                       is one element of the response array,
        #                                       OR `structured` is the parsed value)
        # We prefer structured_content when available and fall back to parsing each
        # TextContent's `.text` as JSON.
        if isinstance(result, tuple) and len(result) == 2:
            content, structured = result
            # `structured` is typically {"result": <parsed>} for list-returning tools
            if isinstance(structured, dict) and "result" in structured and len(structured) == 1:
                return structured["result"]
            if structured is not None:
                return structured
            # Fall through to parsing the content list
            if content and all(hasattr(c, "text") for c in content):
                if len(content) == 1:
                    try:
                        return _json.loads(content[0].text)
                    except Exception:
                        return content[0].text
                return [_json.loads(c.text) for c in content]
            return content
        if result and hasattr(result[0], "text"):
            try:
                return _json.loads(result[0].text)
            except Exception:
                return result[0].text
        return result

    return _call
