"""Sprint service - lifecycle and membership."""

from __future__ import annotations

from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.clock import now as _now
from app.models import Issue, Project, Sprint, SprintIssue, User
from app.services import history, permissions
from app.services.workflows import initial_status_for_project


def list_sprints(db: Session, project_key: Optional[str] = None) -> list[Sprint]:
    q = db.query(Sprint)
    if project_key:
        q = q.filter(Sprint.project_key == project_key)
    return q.order_by(Sprint.start_date.asc().nullslast()).all()


def get_sprint(db: Session, sprint_id: str) -> Sprint:
    s = db.query(Sprint).filter(Sprint.id == sprint_id).one_or_none()
    if s is None:
        raise HTTPException(404, f"Sprint '{sprint_id}' not found.")
    return s


def create_sprint(
    db: Session, actor: User, *, project_key: str, name: str,
    start_date: Optional[datetime] = None, end_date: Optional[datetime] = None,
    goal: Optional[str] = None,
) -> Sprint:
    permissions.require(db, actor, "sprint.create", project_key=project_key)
    s = Sprint(
        id=f"sprint_{project_key.lower()}_{int(_now().timestamp())}",
        project_key=project_key, name=name, state="future",
        start_date=start_date, end_date=end_date, goal=goal,
        created_at=_now(),
    )
    db.add(s)
    db.flush()
    return s


def start_sprint(db: Session, actor: User, sprint_id: str) -> Sprint:
    s = get_sprint(db, sprint_id)
    permissions.require(db, actor, "sprint.start", project_key=s.project_key)
    if s.state == "active":
        return s
    if s.state == "closed":
        raise HTTPException(422, "Cannot start a closed sprint.")
    # At most one active sprint per project
    other_active = (
        db.query(Sprint)
        .filter(Sprint.project_key == s.project_key, Sprint.state == "active", Sprint.id != s.id)
        .first()
    )
    if other_active is not None:
        raise HTTPException(
            422,
            f"Project {s.project_key} already has an active sprint: '{other_active.name}' ({other_active.id}). "
            f"Complete it before starting another.",
        )
    s.state = "active"
    if s.start_date is None:
        s.start_date = _now()
    history.sprint_started(db, actor.id, s.id, s.name)
    db.flush()
    return s


def complete_sprint(
    db: Session, actor: User, sprint_id: str, move_unfinished_to: Optional[str] = None,
) -> Sprint:
    s = get_sprint(db, sprint_id)
    permissions.require(db, actor, "sprint.complete", project_key=s.project_key)
    if s.state == "closed":
        return s
    if s.state == "future":
        raise HTTPException(422, "Cannot complete a sprint that hasn't started.")

    # Move unfinished issues (not in done category) to target sprint or back to backlog
    unfinished_q = (
        db.query(SprintIssue, Issue)
        .join(Issue, SprintIssue.issue_id == Issue.id)
        .filter(SprintIssue.sprint_id == s.id)
    )
    initial = initial_status_for_project(db, s.project_key)
    moved = 0
    for si, issue in unfinished_q.all():
        from app.models import WorkflowStatus
        status_obj = db.query(WorkflowStatus).filter(WorkflowStatus.id == issue.status_id).one()
        if status_obj.category != "done":
            db.delete(si)
            if move_unfinished_to:
                target = get_sprint(db, move_unfinished_to)
                if target.state == "closed":
                    raise HTTPException(422, f"Target sprint '{move_unfinished_to}' is closed.")
                db.add(SprintIssue(
                    sprint_id=target.id, issue_id=issue.id,
                    rank=si.rank, added_at=_now(),
                ))
                history.sprint_removed(db, actor.id, issue.id, s.id)
                history.sprint_added(db, actor.id, issue.id, target.id)
            else:
                # Bounce back to backlog and to the initial status
                history.sprint_removed(db, actor.id, issue.id, s.id)
            moved += 1

    s.state = "closed"
    s.completed_at = _now()
    history.sprint_completed(db, actor.id, s.id, s.name)
    db.flush()
    return s


def add_issues_to_sprint(db: Session, actor: User, sprint_id: str, issue_ids: Iterable[str]) -> Sprint:
    s = get_sprint(db, sprint_id)
    permissions.require(db, actor, "issue.update", project_key=s.project_key)
    if s.state == "closed":
        raise HTTPException(422, "Cannot add issues to a closed sprint.")

    for issue_id in issue_ids:
        issue = db.query(Issue).filter(Issue.id == issue_id).one_or_none()
        if issue is None:
            raise HTTPException(404, f"Issue '{issue_id}' not found.")
        if issue.project_key != s.project_key:
            raise HTTPException(
                422,
                f"Issue {issue.id} belongs to {issue.project_key}, cannot add to sprint in {s.project_key}.",
            )
        existing = (
            db.query(SprintIssue)
            .filter(SprintIssue.sprint_id == s.id, SprintIssue.issue_id == issue.id)
            .one_or_none()
        )
        if existing:
            continue
        # Remove from any other sprint in the same project first
        for other in (
            db.query(SprintIssue)
            .join(Sprint, SprintIssue.sprint_id == Sprint.id)
            .filter(SprintIssue.issue_id == issue.id, Sprint.project_key == s.project_key)
            .all()
        ):
            history.sprint_removed(db, actor.id, issue.id, other.sprint_id)
            db.delete(other)
        db.add(SprintIssue(
            sprint_id=s.id, issue_id=issue.id, rank=f"0|{int(_now().timestamp()):010d}",
            added_at=_now(),
        ))
        history.sprint_added(db, actor.id, issue.id, s.id)
    db.flush()
    return s


def remove_issues_from_sprint(db: Session, actor: User, sprint_id: str, issue_ids: Iterable[str]) -> Sprint:
    s = get_sprint(db, sprint_id)
    permissions.require(db, actor, "issue.update", project_key=s.project_key)
    for issue_id in issue_ids:
        existing = (
            db.query(SprintIssue)
            .filter(SprintIssue.sprint_id == s.id, SprintIssue.issue_id == issue_id)
            .one_or_none()
        )
        if existing:
            db.delete(existing)
            history.sprint_removed(db, actor.id, issue_id, s.id)
    db.flush()
    return s
