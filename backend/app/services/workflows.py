"""Workflow state machine.

Owns:
- Lookups of allowed transitions for an issue in its current status
- Validation that a requested transition is legal
- Guard evaluation (e.g. epic cannot move to Done if subtasks are not Done)
- Denormalization of `board_list` from the target status
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Optional

from fastapi import HTTPException, status as http_status
from sqlalchemy.orm import Session

from app.models import Issue, Project, WorkflowStatus, WorkflowTransition


@dataclass(frozen=True)
class AllowedTransition:
    to_status_id: str
    to_status_name: str
    name: str  # transition label, e.g. "Submit for review"


class TransitionError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def get_workflow_id_for_project(db: Session, project_key: str) -> str:
    p = db.query(Project).filter(Project.key == project_key).one_or_none()
    if p is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Project {project_key} not found.")
    return p.workflow_id


def allowed_transitions_for_issue(db: Session, issue: Issue) -> list[AllowedTransition]:
    workflow_id = get_workflow_id_for_project(db, issue.project_key)
    rows = (
        db.query(WorkflowTransition, WorkflowStatus)
        .join(WorkflowStatus, WorkflowTransition.to_status_id == WorkflowStatus.id)
        .filter(
            WorkflowTransition.workflow_id == workflow_id,
            WorkflowTransition.from_status_id == issue.status_id,
        )
        .all()
    )
    return [AllowedTransition(to_status_id=ws.id, to_status_name=ws.name, name=t.name) for t, ws in rows]


def find_transition_by_target(db: Session, issue: Issue, to_status: str) -> tuple[WorkflowTransition, WorkflowStatus]:
    """Find a transition whose `to_status` matches by id or name. Raise 422 with a helpful list otherwise."""
    workflow_id = get_workflow_id_for_project(db, issue.project_key)

    # Resolve to_status to a WorkflowStatus row (by id or by name)
    target = (
        db.query(WorkflowStatus)
        .filter(
            WorkflowStatus.workflow_id == workflow_id,
            (WorkflowStatus.id == to_status) | (WorkflowStatus.name == to_status),
        )
        .one_or_none()
    )
    if target is None:
        raise TransitionError(
            f"No status named '{to_status}' in workflow for project {issue.project_key}."
        )

    transition = (
        db.query(WorkflowTransition)
        .filter(
            WorkflowTransition.workflow_id == workflow_id,
            WorkflowTransition.from_status_id == issue.status_id,
            WorkflowTransition.to_status_id == target.id,
        )
        .one_or_none()
    )
    if transition is None:
        allowed = allowed_transitions_for_issue(db, issue)
        allowed_names = ", ".join(repr(t.to_status_name) for t in allowed) or "(no transitions defined)"
        raise TransitionError(
            f"Cannot transition {issue.id} from status '{_status_name(db, issue.status_id)}' to "
            f"'{target.name}'. Allowed next statuses: {allowed_names}."
        )
    return transition, target


def evaluate_guards(db: Session, issue: Issue, transition: WorkflowTransition, target: WorkflowStatus) -> None:
    """Raise TransitionError if any guard fails."""
    if not transition.guards_json:
        # Built-in guard: Epic cannot move to a Done-category status if any subtask isn't done.
        if issue.issue_type == "Epic" and target.category == "done":
            child_undone = (
                db.query(Issue)
                .join(WorkflowStatus, Issue.status_id == WorkflowStatus.id)
                .filter(Issue.epic_id == issue.id, WorkflowStatus.category != "done")
                .count()
            )
            if child_undone > 0:
                raise TransitionError(
                    f"Cannot mark Epic {issue.id} as '{target.name}': {child_undone} child issue(s) "
                    f"are not yet done."
                )
        return

    guards = json.loads(transition.guards_json)
    if guards.get("all_subtasks_done") and target.category == "done":
        child_undone = (
            db.query(Issue)
            .join(WorkflowStatus, Issue.status_id == WorkflowStatus.id)
            .filter(Issue.parent_id == issue.id, WorkflowStatus.category != "done")
            .count()
        )
        if child_undone > 0:
            raise TransitionError(
                f"Cannot transition {issue.id}: {child_undone} subtask(s) are not done yet."
            )


def initial_status_for_project(db: Session, project_key: str) -> WorkflowStatus:
    workflow_id = get_workflow_id_for_project(db, project_key)
    s = (
        db.query(WorkflowStatus)
        .filter(WorkflowStatus.workflow_id == workflow_id, WorkflowStatus.is_initial.is_(True))
        .one_or_none()
    )
    if s is None:
        # Fall back to lowest-position
        s = (
            db.query(WorkflowStatus)
            .filter(WorkflowStatus.workflow_id == workflow_id)
            .order_by(WorkflowStatus.position)
            .first()
        )
    if s is None:
        raise HTTPException(500, f"No statuses configured for project {project_key}.")
    return s


def _status_name(db: Session, status_id: str) -> str:
    s = db.query(WorkflowStatus).filter(WorkflowStatus.id == status_id).one_or_none()
    return s.name if s else status_id


def resolve_board_list(db: Session, status_id: str) -> str:
    s = db.query(WorkflowStatus).filter(WorkflowStatus.id == status_id).one()
    return s.board_list
