"""Workflow state machine tests.

Covers:
- Every legal transition succeeds and updates status_id + board_list together
- Illegal transitions raise with a message listing the allowed next statuses
- Epic guard: Epic cannot move to Done while any child is undone
- Resolution auto-set on entering Done, cleared on leaving Done
"""

from __future__ import annotations

import pytest

from app.models import Issue, User, Workflow, WorkflowStatus
from app.services import issues as issue_svc
from app.services import workflows as wf_svc


def _admin(db):
    return db.query(User).filter(User.id == "user_admin").one()


def test_allowed_transitions_for_initial_status(db):
    # A fresh SCRUM issue starts in Backlog and should have at least one allowed transition
    issue = issue_svc.create_issue(
        db, _admin(db),
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="Test"),
    )
    allowed = wf_svc.allowed_transitions_for_issue(db, issue)
    names = sorted(t.to_status_name for t in allowed)
    assert "In Progress" in names
    assert "To Do" in names


def test_every_seeded_transition_is_legal(db):
    """For every (from -> to) row in workflow_transitions, the engine accepts it."""
    from app.models import WorkflowTransition

    admin = _admin(db)
    rows = (
        db.query(WorkflowTransition, WorkflowStatus.name, WorkflowStatus.id)
        .join(WorkflowStatus, WorkflowStatus.id == WorkflowTransition.to_status_id)
        .filter(WorkflowTransition.workflow_id == "wf_software_scrum")
        .all()
    )

    for transition, to_name, _to_id in rows:
        # Spawn a fresh issue and force it into the `from` state by walking shortest paths.
        issue = issue_svc.create_issue(
            db, admin,
            issue_svc.CreateIssueInput(
                project_key="SCRUM", issue_type="Task", summary=f"Probe {to_name}",
            ),
        )
        # Direct shortcut: use a known shortest path. From Backlog we can reach any
        # status in at most 3 steps using {Start work, Submit for review, Approve}.
        path_map = {
            "status_scrum_backlog": [],
            "status_scrum_todo": ["To Do"],
            "status_scrum_inprogress": ["In Progress"],
            "status_scrum_inreview": ["In Progress", "In Review"],
            "status_scrum_done": ["In Progress", "Done"],
        }
        for step in path_map[transition.from_status_id]:
            issue = issue_svc.transition_issue(db, admin, issue.id, step)
        # Now apply the transition under test
        issue = issue_svc.transition_issue(db, admin, issue.id, to_name)
        assert issue.status_id == transition.to_status_id
        # board_list should match the status's board_list column exactly.
        bl = db.query(WorkflowStatus.board_list).filter(WorkflowStatus.id == issue.status_id).scalar()
        assert issue.board_list == bl


def test_illegal_transition_lists_allowed(db):
    issue = issue_svc.create_issue(
        db, _admin(db),
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="Illegal"),
    )
    with pytest.raises(Exception) as ei:
        issue_svc.transition_issue(db, _admin(db), issue.id, "In Review")
    msg = str(getattr(ei.value, "detail", ei.value))
    assert "Allowed next statuses" in msg
    assert "'In Progress'" in msg or "'To Do'" in msg


def test_resolution_auto_set_on_done(db):
    issue = issue_svc.create_issue(
        db, _admin(db),
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="Resolves"),
    )
    issue_svc.transition_issue(db, _admin(db), issue.id, "In Progress")
    issue = issue_svc.transition_issue(db, _admin(db), issue.id, "Done")
    assert issue.resolution == "Fixed"

    issue = issue_svc.transition_issue(db, _admin(db), issue.id, "In Progress")
    assert issue.resolution is None


def test_epic_guard_blocks_done_with_undone_children(db):
    admin = _admin(db)
    epic = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Epic", summary="Guard Epic"),
    )
    child = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(
            project_key="SCRUM", issue_type="Story", summary="Child of guard epic",
            epic_id=epic.id,
        ),
    )

    issue_svc.transition_issue(db, admin, epic.id, "In Progress")
    with pytest.raises(Exception) as ei:
        issue_svc.transition_issue(db, admin, epic.id, "Done")
    assert "Epic" in str(getattr(ei.value, "detail", ei.value))

    # Once the child is Done, the epic can move to Done.
    issue_svc.transition_issue(db, admin, child.id, "In Progress")
    issue_svc.transition_issue(db, admin, child.id, "Done")
    issue_svc.transition_issue(db, admin, epic.id, "Done")  # no raise


def test_support_kanban_transitions(db):
    """Support project uses kanban workflow with different statuses."""
    admin = _admin(db)
    issue = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(project_key="SUP", issue_type="Bug", summary="Support test"),
    )
    assert issue.board_list == "Open"
    issue_svc.transition_issue(db, admin, issue.id, "Triaged")
    issue_svc.transition_issue(db, admin, issue.id, "Working")
    issue_svc.transition_issue(db, admin, issue.id, "Waiting")
    issue_svc.transition_issue(db, admin, issue.id, "Working")
    issue_svc.transition_issue(db, admin, issue.id, "Resolved")
    issue_svc.transition_issue(db, admin, issue.id, "Closed")
    issue_svc.transition_issue(db, admin, issue.id, "Working")  # reopen path

    with pytest.raises(Exception):
        # 'Done' is not a status in the kanban workflow
        issue_svc.transition_issue(db, admin, issue.id, "Done")
