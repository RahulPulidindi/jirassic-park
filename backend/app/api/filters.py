"""Saved-filter routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_session
from app.models import SavedFilter, User
from app.schemas.api import SavedFilterIn, SavedFilterOut

router = APIRouter()


@router.get("", response_model=list[SavedFilterOut])
def list_filters(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    rows = (
        db.query(SavedFilter)
        .filter((SavedFilter.shared.is_(True)) | (SavedFilter.owner_id == user.id))
        .order_by(SavedFilter.name)
        .all()
    )
    return [SavedFilterOut.model_validate(r) for r in rows]


@router.get("/{filter_id}", response_model=SavedFilterOut)
def get_filter(
    filter_id: str,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    f = db.query(SavedFilter).filter(SavedFilter.id == filter_id).one_or_none()
    if f is None:
        # Try name
        f = db.query(SavedFilter).filter(SavedFilter.name == filter_id).one_or_none()
    if f is None:
        raise HTTPException(404, f"Saved filter '{filter_id}' not found.")
    return SavedFilterOut.model_validate(f)


@router.post("", response_model=SavedFilterOut, status_code=201)
def create_filter(
    payload: SavedFilterIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    f = SavedFilter(
        id=f"filter_{uuid.uuid4().hex[:12]}",
        name=payload.name, owner_id=user.id, jql=payload.jql,
        description=payload.description, shared=payload.shared,
    )
    db.add(f)
    db.commit()
    return SavedFilterOut.model_validate(f)
