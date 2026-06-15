"""Search route: GET /api/search?jql=...&limit=&offset=

Also exposes POST /api/search/bulk_transition and POST /api/search/bulk_assign
for atomic, audited bulk operations from REST and MCP.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api._helpers import issue_to_out
from app.auth import get_current_user
from app.db import get_session
from app.models import User
from app.schemas.api import (
    BulkAssignIn,
    BulkResultOut,
    BulkTransitionIn,
    SearchOut,
)
from app.services import issues as issue_svc
from app.services.search import search

router = APIRouter()


@router.get("", response_model=SearchOut)
def search_route(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    jql: Annotated[str, Query(description="JQL-lite query string")] = "",
    limit: int = 50,
    offset: int = 0,
):
    rows, total = search(db, jql, current_user=user, limit=limit, offset=offset)
    return SearchOut(
        jql=jql, total=total, limit=limit, offset=offset,
        issues=[issue_to_out(db, i) for i in rows],
    )


@router.post("/bulk_transition", response_model=BulkResultOut)
def bulk_transition(
    payload: BulkTransitionIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    rows, total = search(db, payload.jql, current_user=user, limit=1000, offset=0)
    failed: list[dict[str, str]] = []
    ok = 0
    for issue in rows:
        try:
            issue_svc.transition_issue(db, user, issue.id, payload.to_status, payload.comment)
            ok += 1
        except Exception as e:
            failed.append({"issue_id": issue.id, "error": str(getattr(e, "detail", e))})
    db.commit()
    return BulkResultOut(total_matched=total, succeeded=ok, failed=failed)


@router.post("/bulk_assign", response_model=BulkResultOut)
def bulk_assign(
    payload: BulkAssignIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    rows, total = search(db, payload.jql, current_user=user, limit=1000, offset=0)
    failed: list[dict[str, str]] = []
    ok = 0
    for issue in rows:
        try:
            issue_svc.assign_issue(db, user, issue.id, payload.assignee)
            ok += 1
        except Exception as e:
            failed.append({"issue_id": issue.id, "error": str(getattr(e, "detail", e))})
    db.commit()
    return BulkResultOut(total_matched=total, succeeded=ok, failed=failed)
