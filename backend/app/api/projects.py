"""Project routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_session
from app.models import Activity, Issue, Project, Sprint, SprintIssue, User, WorkflowStatus
from app.schemas.api import (
    ActivityOut,
    ProjectCreateIn,
    ProjectOut,
    ProjectPatchIn,
    ProjectSummaryOut,
    SprintOut,
    WorkflowOut,
)
from app.services import projects as projects_svc

router = APIRouter()


@router.get("", response_model=list[ProjectOut])
def list_projects(
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    return [ProjectOut.model_validate(p) for p in projects_svc.list_projects(db)]


@router.get("/{key}", response_model=ProjectOut)
def get_project(
    key: str,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    return ProjectOut.model_validate(projects_svc.get_project(db, key))


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectCreateIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    p = projects_svc.create_project(
        db, user, key=payload.key, name=payload.name, description=payload.description,
        workflow_id=payload.workflow_id, lead_id=payload.lead_id, project_type=payload.project_type,
    )
    db.commit()
    return ProjectOut.model_validate(p)


@router.patch("/{key}", response_model=ProjectOut)
def update_project(
    key: str,
    payload: ProjectPatchIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    p = projects_svc.update_project(db, user, key, payload.model_dump(exclude_unset=True))
    db.commit()
    return ProjectOut.model_validate(p)


@router.get("/{key}/workflow", response_model=WorkflowOut)
def project_workflow(
    key: str,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    p = projects_svc.get_project(db, key)
    wf = p.workflow
    out = WorkflowOut.model_validate(wf)
    return out


@router.get("/{key}/summary", response_model=ProjectSummaryOut)
def project_summary(
    key: str,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    project = projects_svc.get_project(db, key)
    total = db.query(Issue).filter(Issue.project_key == key).count()

    # by status (use status name not id)
    rows = (
        db.query(WorkflowStatus.name, func.count(Issue.id))
        .join(Issue, Issue.status_id == WorkflowStatus.id)
        .filter(Issue.project_key == key)
        .group_by(WorkflowStatus.name)
        .all()
    )
    by_status = {name: cnt for name, cnt in rows}

    rows = (
        db.query(Issue.priority, func.count(Issue.id))
        .filter(Issue.project_key == key)
        .group_by(Issue.priority)
        .all()
    )
    by_priority = {p: c for p, c in rows}

    rows = (
        db.query(Issue.owner, func.count(Issue.id))
        .filter(Issue.project_key == key)
        .group_by(Issue.owner)
        .all()
    )
    by_assignee = {(owner or "unassigned"): cnt for owner, cnt in rows}

    active_sprint = (
        db.query(Sprint).filter(Sprint.project_key == key, Sprint.state == "active").first()
    )
    progress = None
    if active_sprint is not None:
        # Count by status for issues in the active sprint
        sub = (
            db.query(WorkflowStatus.category, func.count(Issue.id))
            .join(Issue, Issue.status_id == WorkflowStatus.id)
            .join(SprintIssue, SprintIssue.issue_id == Issue.id)
            .filter(SprintIssue.sprint_id == active_sprint.id)
            .group_by(WorkflowStatus.category)
            .all()
        )
        progress = {cat: cnt for cat, cnt in sub}

    recent = (
        db.query(Activity)
        .join(Issue, Issue.id == Activity.issue_id, isouter=True)
        .filter(Issue.project_key == key)
        .order_by(Activity.created_at.desc())
        .limit(15)
        .all()
    )

    return ProjectSummaryOut(
        project=ProjectOut.model_validate(project),
        total_issues=total,
        by_status=by_status,
        by_priority=by_priority,
        by_assignee=by_assignee,
        active_sprint=SprintOut.model_validate(active_sprint) if active_sprint else None,
        active_sprint_progress=progress,
        recent_activity=[ActivityOut.model_validate(a) for a in recent],
    )
