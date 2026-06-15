"""User listing and per-user notifications (mentions)."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_session
from app.models import Activity, User
from app.schemas.api import ActivityOut, UserOut

router = APIRouter()


@router.get("", response_model=list[UserOut])
def list_users(
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    return [UserOut.model_validate(u) for u in db.query(User).order_by(User.name).all()]


@router.get("/me/mentions", response_model=list[ActivityOut])
def my_mentions(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    limit: int = 50,
    since: Optional[str] = None,
):
    """Recent `@user` mentions for the current user, newest first.

    Powers the bell icon in the UI top bar and `jira_my_mentions` in MCP.
    """
    q = (
        db.query(Activity)
        .filter(Activity.action == "mentioned", Activity.to_value == user.id)
        .order_by(Activity.created_at.desc())
    )
    if since:
        from datetime import datetime
        try:
            cutoff = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError as e:
            raise HTTPException(422, f"Invalid 'since' timestamp: {e}") from None
        q = q.filter(Activity.created_at > cutoff.replace(tzinfo=None))
    return [ActivityOut.model_validate(a) for a in q.limit(limit).all()]


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: str,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    u = db.query(User).filter(User.id == user_id).one_or_none()
    if u is None:
        raise HTTPException(404, f"User '{user_id}' not found.")
    return UserOut.model_validate(u)
