"""Jira-shape error responses.

Real Jira returns errors as:
    HTTP 4xx { "errorMessages": ["..."], "errors": { "field": "msg" } }

FastAPI's default is `{ "detail": "..." }`. Agents trained on real Jira pattern-
match the former shape; this module is the translator.

We register the handler only on the /rest/api/3/* surface so the legacy
`/api/*` endpoints (used by the React frontend) keep their existing behavior.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


def jira_envelope(error_messages: list[str] | None = None,
                  errors: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "errorMessages": list(error_messages or []),
        "errors": dict(errors or {}),
    }


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Convert FastAPI/Starlette HTTPException -> Jira envelope."""
    detail = exc.detail
    if isinstance(detail, dict) and ("errorMessages" in detail or "errors" in detail):
        # Already in the right shape (caller pre-built it).
        body = {
            "errorMessages": list(detail.get("errorMessages") or []),
            "errors": dict(detail.get("errors") or {}),
        }
    elif isinstance(detail, dict):
        body = jira_envelope(errors={k: str(v) for k, v in detail.items()})
    elif isinstance(detail, list):
        body = jira_envelope(error_messages=[str(d) for d in detail])
    else:
        # Common case: detail is a plain string.
        text = str(detail) if detail else _default_message_for_status(exc.status_code)
        # Jira's well-known "soft-404" message for permission-hidden issues.
        # Surfacing it verbatim helps agents that grep on the canonical wording.
        if exc.status_code == status.HTTP_404_NOT_FOUND and "issue" in text.lower():
            text = "Issue does not exist or you do not have permission to see it."
        body = jira_envelope(error_messages=[text])
    return JSONResponse(status_code=exc.status_code, content=body)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Translate Pydantic validation errors to Jira's `errors` object keyed by field."""
    errors: dict[str, str] = {}
    messages: list[str] = []
    for e in exc.errors():
        # `loc` is like ("body", "fields", "summary"). We pick the last
        # path component as the field name, which matches what Jira returns.
        loc = e.get("loc") or ()
        field = loc[-1] if loc else "error"
        msg = e.get("msg", "Invalid value")
        if field == "error":
            messages.append(msg)
        else:
            errors[str(field)] = msg
    if not errors and not messages:
        messages.append("Request validation failed.")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=jira_envelope(error_messages=messages, errors=errors),
    )


def _default_message_for_status(code: int) -> str:
    return {
        400: "Bad Request",
        401: "You are not authorized to access this resource.",
        403: "You do not have permission to perform this action.",
        404: "The requested resource was not found.",
        409: "Conflict.",
        422: "Validation failed.",
    }.get(code, "Internal server error.")
