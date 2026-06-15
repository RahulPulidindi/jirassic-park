"""Helpers for building rich response shapes from ORM rows."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import Activity, Comment, Issue, IssueLabel, Sprint, SprintIssue, Watcher, WorkflowStatus
from app.schemas.api import AllowedTransitionOut, CommentOut, IssueDetailOut, IssueLinkOut, IssueOut


def labels_for_issue(db: Session, issue_id: str) -> list[str]:
    rows = db.query(IssueLabel.label_name).filter(IssueLabel.issue_id == issue_id).all()
    return sorted(r[0] for r in rows)


def watchers_for_issue(db: Session, issue_id: str) -> list[str]:
    rows = db.query(Watcher.user_id).filter(Watcher.issue_id == issue_id).all()
    return [r[0] for r in rows]


def sprint_for_issue(db: Session, issue_id: str) -> tuple[Optional[str], Optional[str]]:
    row = (
        db.query(Sprint)
        .join(SprintIssue, SprintIssue.sprint_id == Sprint.id)
        .filter(SprintIssue.issue_id == issue_id)
        .first()
    )
    return (row.id, row.name) if row else (None, None)


def status_name_for(db: Session, status_id: str) -> str:
    s = db.query(WorkflowStatus).filter(WorkflowStatus.id == status_id).one_or_none()
    return s.name if s else status_id


def issue_to_out(db: Session, issue: Issue) -> IssueOut:
    sprint_id, _ = sprint_for_issue(db, issue.id)
    return IssueOut(
        id=issue.id, project_key=issue.project_key, issue_type=issue.issue_type,
        summary=issue.summary, description=issue.description,
        status_id=issue.status_id, status=status_name_for(db, issue.status_id),
        board_list=issue.board_list, priority=issue.priority,
        owner=issue.owner, reporter=issue.reporter,
        parent_id=issue.parent_id, epic_id=issue.epic_id,
        story_points=issue.story_points, resolution=issue.resolution,
        due_date=issue.due_date,
        labels=labels_for_issue(db, issue.id),
        watchers=watchers_for_issue(db, issue.id),
        sprint_id=sprint_id,
        created_at=issue.created_at, updated_at=issue.updated_at,
    )


def issue_to_detail(db: Session, issue: Issue) -> IssueDetailOut:
    from app.services import workflows

    base = issue_to_out(db, issue)
    sprint_id, sprint_name = sprint_for_issue(db, issue.id)

    allowed = workflows.allowed_transitions_for_issue(db, issue)
    recent_comments = (
        db.query(Comment)
        .filter(Comment.issue_id == issue.id)
        .order_by(Comment.created_at.desc())
        .limit(20)
        .all()
    )
    return IssueDetailOut(
        **base.model_dump(),
        allowed_transitions=[
            AllowedTransitionOut(to_status_id=t.to_status_id, to_status_name=t.to_status_name, name=t.name)
            for t in allowed
        ],
        outbound_links=[IssueLinkOut.model_validate(l) for l in issue.outbound_links],
        inbound_links=[IssueLinkOut.model_validate(l) for l in issue.inbound_links],
        recent_comments=[CommentOut.model_validate(c) for c in reversed(recent_comments)],
        sprint_name=sprint_name,
    )


def history_for_issue(db: Session, issue_id: str, limit: int = 50) -> list[Activity]:
    return (
        db.query(Activity)
        .filter(Activity.issue_id == issue_id)
        .order_by(Activity.created_at.desc())
        .limit(limit)
        .all()
    )
