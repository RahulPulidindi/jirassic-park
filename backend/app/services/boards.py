"""Board service - snapshots a board into columns and cards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Board, Issue, Project, Sprint, SprintIssue, WorkflowStatus


@dataclass
class BoardCard:
    issue: Issue


@dataclass
class BoardColumn:
    status_name: str
    board_list: str
    category: str
    color: str
    cards: list[BoardCard]


@dataclass
class BoardSnapshot:
    board: Board
    project: Project
    active_sprint: Optional[Sprint]
    columns: list[BoardColumn]


def list_boards(db: Session, project_key: Optional[str] = None) -> list[Board]:
    q = db.query(Board)
    if project_key:
        q = q.filter(Board.project_key == project_key)
    return q.order_by(Board.name).all()


def get_board(db: Session, board_id: str) -> Board:
    b = db.query(Board).filter(Board.id == board_id).one_or_none()
    if b is None:
        raise HTTPException(404, f"Board '{board_id}' not found.")
    return b


def snapshot_board(db: Session, board_id: str) -> BoardSnapshot:
    """Materialize a board into columns of cards.

    For scrum boards: show only the active sprint's issues.
    For kanban boards: show every non-Closed issue.
    """
    board = get_board(db, board_id)
    project = db.query(Project).filter(Project.key == board.project_key).one()
    statuses = (
        db.query(WorkflowStatus)
        .filter(WorkflowStatus.workflow_id == project.workflow_id)
        .order_by(WorkflowStatus.position)
        .all()
    )

    active_sprint = (
        db.query(Sprint)
        .filter(Sprint.project_key == project.key, Sprint.state == "active")
        .order_by(Sprint.start_date.desc().nullslast())
        .first()
    )

    if board.board_type == "scrum" and active_sprint is not None:
        issues = (
            db.query(Issue)
            .join(SprintIssue, SprintIssue.issue_id == Issue.id)
            .filter(SprintIssue.sprint_id == active_sprint.id)
            .all()
        )
    elif board.board_type == "kanban":
        # All non-closed issues in the project
        closed_status_ids = [s.id for s in statuses if s.category == "done" and s.name == "Closed"]
        q = db.query(Issue).filter(Issue.project_key == project.key)
        if closed_status_ids:
            q = q.filter(~Issue.status_id.in_(closed_status_ids))
        issues = q.all()
    else:
        # scrum without an active sprint: empty board
        issues = []

    # Group by status
    by_status: dict[str, list[Issue]] = {s.id: [] for s in statuses}
    for issue in issues:
        by_status.setdefault(issue.status_id, []).append(issue)

    columns = []
    for s in statuses:
        columns.append(
            BoardColumn(
                status_name=s.name, board_list=s.board_list, category=s.category, color=s.color,
                cards=[BoardCard(issue=i) for i in by_status.get(s.id, [])],
            )
        )

    return BoardSnapshot(board=board, project=project, active_sprint=active_sprint, columns=columns)
