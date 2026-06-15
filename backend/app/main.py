"""FastAPI application entrypoint.

Mounts:
- /api/*  -> REST routes (thin shims over services)
- /mcp    -> MCP server (FastMCP over Streamable HTTP)
- /       -> Next.js static export
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import router as api_router
from app.api.jira_compat import router as jira_compat_router
from app.api.jira_compat.errors import (
    http_exception_handler as jira_http_exception_handler,
    validation_exception_handler as jira_validation_exception_handler,
)
from app.config import settings
from app.db import init_engine
from app.mcp.server import build_mcp, mount_mcp


logger = logging.getLogger("jirassic_park")


def create_app() -> FastAPI:
    s = settings()
    mcp = build_mcp()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Bring up the SQLite engine and run the MCP session manager for the
        # lifetime of the process. Without the latter, every /mcp request
        # raises "Task group is not initialized."
        init_engine()
        logger.info("Jirassic Park ready. data_dir=%s", s.data_dir)
        async with mcp.session_manager.run():
            yield

    app = FastAPI(
        title="Jirassic Park",
        description=(
            "A Jira-like environment for humans and agents. Three convergent "
            "surfaces (browser UI, REST API, MCP) over a shared service layer "
            "and one SQLite database."
        ),
        version="0.1.0",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "jirassic-park"}

    @app.get("/api/clock")
    def get_clock() -> dict:
        """Public read of the universal clock. Useful as a fast probe for
        researchers to confirm the env is pinned, and for the UI to render
        'relative time' values consistently across surfaces."""
        from app import clock
        return clock.describe()

    # REST API
    app.include_router(api_router, prefix="/api")

    # Atlassian-compat REST surface at /rest/api/3 — same service layer,
    # Jira-shaped requests/responses/errors. Agents trained against this
    # surface can drop into a real Jira instance without rewriting their
    # request/response handlers. See app/api/jira_compat/__init__.py.
    app.include_router(jira_compat_router, prefix="/rest/api/3", tags=["jira-compat"])

    # Route-scoped Jira-shape error handlers. We register them at the app
    # level (FastAPI doesn't support per-prefix handlers) and short-circuit
    # to the default behavior for legacy /api/* paths so the existing UI
    # keeps seeing `{detail: ...}`.
    @app.exception_handler(StarletteHTTPException)
    async def _on_http_exc(request, exc):
        if request.url.path.startswith("/rest/api/"):
            return await jira_http_exception_handler(request, exc)
        # Default behaviour: re-raise so FastAPI's built-in handler runs.
        from fastapi.exception_handlers import http_exception_handler as default_handler
        return await default_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _on_validation(request, exc):
        if request.url.path.startswith("/rest/api/"):
            return await jira_validation_exception_handler(request, exc)
        from fastapi.exception_handlers import request_validation_exception_handler as default_handler
        return await default_handler(request, exc)

    # MCP server at /mcp (lifespan above keeps its session manager running)
    mount_mcp(app, mcp)

    # Static UI at /
    static_dir = Path(s.static_dir)
    if static_dir.exists():
        # Custom SPA-style handler: serve static files first, fall through to index.html
        # for client-side routes.
        app.mount(
            "/_next",
            StaticFiles(directory=str(static_dir / "_next"), check_dir=False),
            name="next-assets",
        )

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(static_dir / "index.html")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str):
            # Disallow falling through to UI for /api, /rest/api, /mcp paths.
            if full_path.startswith(("api/", "rest/api/", "mcp", "health")):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            # Static asset?
            candidate = static_dir / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            # Next.js exports a .html file per route by default
            html_candidate = static_dir / f"{full_path}.html"
            if html_candidate.is_file():
                return FileResponse(html_candidate)
            # Otherwise serve index for client routing
            return FileResponse(static_dir / "index.html")
    else:
        logger.warning("Static UI not found at %s — UI routes disabled", static_dir)

    return app


app = create_app()
