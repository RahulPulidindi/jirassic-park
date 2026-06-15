"""Project service."""

from __future__ import annotations

from app.clock import now as _now
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Project, User
from app.services import permissions


def list_projects(db: Session) -> list[Project]:
    return db.query(Project).order_by(Project.key).all()


def get_project(db: Session, key: str) -> Project:
    p = db.query(Project).filter(Project.key == key).one_or_none()
    if p is None:
        raise HTTPException(404, f"Project '{key}' not found.")
    return p


def create_project(
    db: Session,
    actor: User,
    *,
    key: str,
    name: str,
    description: Optional[str],
    workflow_id: str,
    lead_id: Optional[str] = None,
    project_type: str = "software",
) -> Project:
    permissions.require(db, actor, "project.create")
    if db.query(Project).filter(Project.key == key).one_or_none() is not None:
        raise HTTPException(409, f"Project key '{key}' already exists.")
    p = Project(
        key=key, name=name, description=description, workflow_id=workflow_id,
        lead_id=lead_id, project_type=project_type, next_issue_number=1,
        created_at=_now(), updated_at=_now(),
    )
    db.add(p)
    db.flush()
    return p


def update_project(db: Session, actor: User, key: str, patch: dict) -> Project:
    p = get_project(db, key)
    permissions.require(db, actor, "project.create")  # reuse: admins only
    for k in ("name", "description", "lead_id", "default_assignee", "avatar_color"):
        if k in patch:
            setattr(p, k, patch[k])
    p.updated_at = _now()
    db.flush()
    return p
