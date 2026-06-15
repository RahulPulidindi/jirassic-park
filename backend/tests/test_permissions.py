"""Permission boundary tests."""

from __future__ import annotations

import pytest

from app.models import User
from app.services import issues as issue_svc
from app.services import sprints as sprint_svc


def _user(db, uid):
    return db.query(User).filter(User.id == uid).one()


def test_viewer_cannot_transition(db):
    observer = _user(db, "user_observer")
    issue = (
        db.query(__import__("app.models", fromlist=["Issue"]).Issue)
        .filter_by(project_key="SCRUM")
        .first()
    )
    with pytest.raises(Exception) as ei:
        issue_svc.transition_issue(db, observer, issue.id, "In Progress")
    msg = str(getattr(ei.value, "detail", ei.value))
    assert "Viewers" in msg


def test_viewer_cannot_create(db):
    observer = _user(db, "user_observer")
    with pytest.raises(Exception) as ei:
        issue_svc.create_issue(
            db, observer,
            issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="No"),
        )
    msg = str(getattr(ei.value, "detail", ei.value))
    assert "Viewers" in msg or "permission" in msg.lower()


def test_viewer_cannot_comment(db):
    observer = _user(db, "user_observer")
    from app.models import Issue
    issue = db.query(Issue).first()
    with pytest.raises(Exception):
        issue_svc.add_comment(db, observer, issue.id, "should fail")


def test_non_lead_cannot_start_sprint(db):
    """sprint.start requires lead/admin on the project."""
    from app.models import Sprint
    sprint = (
        db.query(Sprint).filter(Sprint.project_key == "SCRUM", Sprint.state == "future").first()
    )
    assert sprint is not None
    devon = _user(db, "user_devon_lee")  # lead of SUP, not SCRUM
    with pytest.raises(Exception) as ei:
        sprint_svc.start_sprint(db, devon, sprint.id)
    msg = str(getattr(ei.value, "detail", ei.value))
    assert "lead" in msg.lower() or "admin" in msg.lower()


def test_admin_can_do_anything(db):
    admin = _user(db, "user_admin")
    issue = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(project_key="SUP", issue_type="Bug", summary="Admin SUP"),
    )
    issue_svc.transition_issue(db, admin, issue.id, "Triaged")  # admin can transition any project
    issue_svc.add_comment(db, admin, issue.id, "Admin comment OK")


def test_admin_reset_requires_admin(client):
    # observer cannot reset
    r = client.post("/api/admin/reset", headers={"Authorization": "Bearer token_observer"})
    assert r.status_code == 403
    # admin can
    r = client.post("/api/admin/reset", headers={"Authorization": "Bearer admin-token-jurassic"})
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_invalid_token_returns_401(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer bogus"})
    assert r.status_code == 401
