"""Audit log tests.

Every mutating service call should write exactly the expected `activities` row.
"""

from __future__ import annotations

from app.models import Activity, User
from app.services import issues as issue_svc


def _admin(db):
    return db.query(User).filter(User.id == "user_admin").one()


def _activity_actions(db, issue_id: str) -> list[str]:
    return [
        a.action
        for a in db.query(Activity)
        .filter(Activity.issue_id == issue_id)
        .order_by(Activity.created_at)
        .all()
    ]


def test_create_logs_created(db):
    admin = _admin(db)
    issue = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="Audit create"),
    )
    assert _activity_actions(db, issue.id) == ["created"]


def test_create_with_owner_logs_created_then_assigned(db):
    admin = _admin(db)
    issue = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(
            project_key="SCRUM", issue_type="Task", summary="Audit assign on create",
            owner="user_priya_iyer",
        ),
    )
    assert _activity_actions(db, issue.id) == ["created", "assigned"]


def test_transition_logs_transitioned(db):
    admin = _admin(db)
    issue = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="Audit trans"),
    )
    issue = issue_svc.transition_issue(db, admin, issue.id, "In Progress")
    rows = (
        db.query(Activity)
        .filter(Activity.issue_id == issue.id, Activity.action == "transitioned")
        .all()
    )
    assert len(rows) == 1
    assert rows[0].from_value == "Backlog"
    assert rows[0].to_value == "In Progress"
    assert rows[0].field == "status"


def test_comment_with_transition_writes_both(db):
    admin = _admin(db)
    issue = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="Audit txn+comment"),
    )
    issue_svc.transition_issue(db, admin, issue.id, "In Progress", "while at it")
    actions = _activity_actions(db, issue.id)
    assert actions == ["created", "transitioned", "commented"]


def test_assign_then_unassign_logged_separately(db):
    admin = _admin(db)
    issue = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="Audit assign roundtrip"),
    )
    issue_svc.assign_issue(db, admin, issue.id, "user_priya_iyer")
    issue_svc.assign_issue(db, admin, issue.id, None)
    rows = (
        db.query(Activity)
        .filter(Activity.issue_id == issue.id, Activity.action == "assigned")
        .order_by(Activity.created_at)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].to_value == "user_priya_iyer"
    assert rows[1].to_value is None
    assert rows[1].from_value == "user_priya_iyer"


def test_link_logs_linked_with_target(db):
    admin = _admin(db)
    a = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="A"),
    )
    b = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="B"),
    )
    issue_svc.link_issues(db, admin, a.id, b.id, "blocks")
    rows = (
        db.query(Activity)
        .filter(Activity.issue_id == a.id, Activity.action == "linked")
        .all()
    )
    assert len(rows) == 1
    assert rows[0].to_value == f"blocks:{b.id}"


def test_update_reporter_logged(db):
    admin = _admin(db)
    issue = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="Audit reporter"),
    )
    issue = issue_svc.update_issue(db, admin, issue.id, {"reporter": "user_priya_iyer"})
    assert issue.reporter == "user_priya_iyer"
    rows = (
        db.query(Activity)
        .filter(Activity.issue_id == issue.id, Activity.action == "updated", Activity.field == "reporter")
        .all()
    )
    assert len(rows) == 1
    assert rows[0].from_value == "user_admin"
    assert rows[0].to_value == "user_priya_iyer"


def test_update_reporter_validates_user(db):
    admin = _admin(db)
    issue = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="Audit reporter bad"),
    )
    import pytest
    with pytest.raises(Exception) as ei:
        issue_svc.update_issue(db, admin, issue.id, {"reporter": "user_who"})
    assert "not a known user" in str(getattr(ei.value, "detail", ei.value))


def test_set_sprint_moves_issue(db):
    from app.models import Sprint, SprintIssue
    admin = _admin(db)
    issue = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="Audit sprint"),
    )
    s_future = db.query(Sprint).filter(Sprint.project_key == "SCRUM", Sprint.state == "future").first()
    s_active = db.query(Sprint).filter(Sprint.project_key == "SCRUM", Sprint.state == "active").first()
    assert s_future is not None and s_active is not None

    issue_svc.set_sprint(db, admin, issue.id, s_future.id)
    assert {si.sprint_id for si in db.query(SprintIssue).filter_by(issue_id=issue.id)} == {s_future.id}

    issue_svc.set_sprint(db, admin, issue.id, s_active.id)
    assert {si.sprint_id for si in db.query(SprintIssue).filter_by(issue_id=issue.id)} == {s_active.id}

    issue_svc.set_sprint(db, admin, issue.id, None)
    assert db.query(SprintIssue).filter_by(issue_id=issue.id).count() == 0

    actions = (
        db.query(Activity.action, Activity.to_value)
        .filter(Activity.issue_id == issue.id, Activity.action.in_(["sprint_added", "sprint_removed"]))
        .order_by(Activity.created_at)
        .all()
    )
    # add to future, remove from future, add to active, remove from active
    assert [a[0] for a in actions] == [
        "sprint_added", "sprint_removed", "sprint_added", "sprint_removed",
    ]


def test_set_sprint_rejects_cross_project(db):
    from app.models import Sprint
    admin = _admin(db)
    issue = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="Cross-project"),
    )
    plat_sprint = db.query(Sprint).filter(Sprint.project_key == "PLAT").first()
    assert plat_sprint is not None
    import pytest
    with pytest.raises(Exception) as ei:
        issue_svc.set_sprint(db, admin, issue.id, plat_sprint.id)
    assert "project" in str(getattr(ei.value, "detail", ei.value)).lower()


def test_label_add_remove_logged(db):
    admin = _admin(db)
    issue = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="lbl"),
    )
    issue_svc.add_label(db, admin, issue.id, "freshlabel")
    issue_svc.remove_label(db, admin, issue.id, "freshlabel")
    rows = (
        db.query(Activity)
        .filter(Activity.issue_id == issue.id, Activity.action.in_(["labeled", "unlabeled"]))
        .order_by(Activity.created_at)
        .all()
    )
    assert [r.action for r in rows] == ["labeled", "unlabeled"]
    assert rows[0].to_value == "freshlabel"
    assert rows[1].from_value == "freshlabel"
