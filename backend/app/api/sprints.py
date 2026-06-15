"""Sprint routes."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api._helpers import issue_to_out
from app.auth import get_current_user
from app.db import get_session
from app.models import Issue, SprintIssue, User
from app.schemas.api import (
    IssueOut,
    SprintAddIssuesIn,
    SprintCompleteIn,
    SprintCreateIn,
    SprintOut,
)
from app.services import sprints as sprint_svc

router = APIRouter()


@router.get("", response_model=list[SprintOut])
def list_sprints(
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    project_key: Optional[str] = None,
):
    return [SprintOut.model_validate(s) for s in sprint_svc.list_sprints(db, project_key)]


@router.get("/{sprint_id}", response_model=SprintOut)
def get_sprint(
    sprint_id: str,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    return SprintOut.model_validate(sprint_svc.get_sprint(db, sprint_id))


@router.get("/{sprint_id}/issues", response_model=list[IssueOut])
def get_sprint_issues(
    sprint_id: str,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    sprint_svc.get_sprint(db, sprint_id)
    issues = (
        db.query(Issue)
        .join(SprintIssue, SprintIssue.issue_id == Issue.id)
        .filter(SprintIssue.sprint_id == sprint_id)
        .all()
    )
    return [issue_to_out(db, i) for i in issues]


@router.post("", response_model=SprintOut, status_code=201)
def create_sprint(
    payload: SprintCreateIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    s = sprint_svc.create_sprint(
        db, user, project_key=payload.project_key, name=payload.name,
        start_date=payload.start_date, end_date=payload.end_date, goal=payload.goal,
    )
    db.commit()
    return SprintOut.model_validate(s)


@router.post("/{sprint_id}/start", response_model=SprintOut)
def start_sprint(
    sprint_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    s = sprint_svc.start_sprint(db, user, sprint_id)
    db.commit()
    return SprintOut.model_validate(s)


@router.post("/{sprint_id}/complete", response_model=SprintOut)
def complete_sprint(
    sprint_id: str,
    payload: SprintCompleteIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    s = sprint_svc.complete_sprint(db, user, sprint_id, payload.move_unfinished_to)
    db.commit()
    return SprintOut.model_validate(s)


@router.post("/{sprint_id}/issues", response_model=SprintOut)
def add_to_sprint(
    sprint_id: str,
    payload: SprintAddIssuesIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    s = sprint_svc.add_issues_to_sprint(db, user, sprint_id, payload.issue_ids)
    db.commit()
    return SprintOut.model_validate(s)


@router.delete("/{sprint_id}/issues", response_model=SprintOut)
def remove_from_sprint(
    sprint_id: str,
    payload: SprintAddIssuesIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    s = sprint_svc.remove_issues_from_sprint(db, user, sprint_id, payload.issue_ids)
    db.commit()
    return SprintOut.model_validate(s)
