"""Board routes."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api._helpers import issue_to_out
from app.auth import get_current_user
from app.db import get_session
from app.models import Board, User
from app.schemas.api import (
    BoardCardOut,
    BoardColumnOut,
    BoardSnapshotOut,
    SprintOut,
)
from app.services import boards as boards_svc

router = APIRouter()


@router.get("", response_model=list[dict])
def list_boards(
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    project_key: Optional[str] = None,
):
    return [
        {
            "id": b.id, "project_key": b.project_key, "name": b.name,
            "board_type": b.board_type, "filter_jql": b.filter_jql,
        }
        for b in boards_svc.list_boards(db, project_key)
    ]


@router.get("/{board_id}", response_model=BoardSnapshotOut)
def get_board(
    board_id: str,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    snap = boards_svc.snapshot_board(db, board_id)
    return BoardSnapshotOut(
        board_id=snap.board.id, project_key=snap.project.key,
        board_type=snap.board.board_type,
        active_sprint=SprintOut.model_validate(snap.active_sprint) if snap.active_sprint else None,
        columns=[
            BoardColumnOut(
                status_name=col.status_name, board_list=col.board_list,
                category=col.category, color=col.color,
                cards=[BoardCardOut(issue=issue_to_out(db, c.issue)) for c in col.cards],
            )
            for col in snap.columns
        ],
    )
