"""Tests for @mention parsing and the per-user notifications feed."""

from __future__ import annotations

import pytest

from app.models import Activity, Comment, User
from app.services import issues as issue_svc


def _user(db, uid: str) -> User:
    return db.query(User).filter(User.id == uid).one()


def _new_issue(db, actor: User):
    return issue_svc.create_issue(
        db, actor,
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="Mention me"),
    )


def test_extract_mentions_canonical_user_id(db):
    admin = _user(db, "user_admin")
    out = issue_svc.extract_mentions(db, "Hey @user_sarah_kim please review.")
    assert out == ["user_sarah_kim"]


def test_extract_mentions_handle_form(db):
    out = issue_svc.extract_mentions(db, "ping @sarah_kim and @marcus_obrien")
    assert out == ["user_sarah_kim", "user_marcus_obrien"]


def test_extract_mentions_handles_punctuation(db):
    out = issue_svc.extract_mentions(db, "ping @sarah_kim, also @priya_iyer.")
    assert out == ["user_sarah_kim", "user_priya_iyer"]


def test_extract_mentions_email_not_mistaken_for_mention(db):
    # `foo@user_sarah_kim` is an email-shape, not a mention. Anchor on word
    # boundary so we don't grab the username part of an email.
    out = issue_svc.extract_mentions(db, "see eng@user_sarah_kim for context")
    assert out == []


def test_extract_mentions_dedupes_and_skips_unknown(db):
    out = issue_svc.extract_mentions(
        db, "@sarah_kim @sarah_kim @nobody @user_priya_iyer"
    )
    assert out == ["user_sarah_kim", "user_priya_iyer"]


def test_add_comment_persists_mentions_and_emits_activity(db):
    admin = _user(db, "user_admin")
    issue = _new_issue(db, admin)
    c = issue_svc.add_comment(db, admin, issue.id, "Heads up @sarah_kim and @priya_iyer.")
    saved = db.query(Comment).filter(Comment.id == c.id).one()
    assert saved.mentions == ["user_sarah_kim", "user_priya_iyer"]

    rows = (
        db.query(Activity)
        .filter(Activity.action == "mentioned", Activity.issue_id == issue.id)
        .order_by(Activity.created_at)
        .all()
    )
    targets = [r.to_value for r in rows]
    assert targets == ["user_sarah_kim", "user_priya_iyer"]
    for r in rows:
        assert r.actor_id == "user_admin"
        assert "Heads up" in (r.comment_body or "")


def test_self_mentions_do_not_notify(db):
    sarah = _user(db, "user_sarah_kim")
    issue = _new_issue(db, sarah)
    issue_svc.add_comment(db, sarah, issue.id, "noting for myself @sarah_kim.")
    rows = (
        db.query(Activity)
        .filter(Activity.action == "mentioned", Activity.issue_id == issue.id)
        .all()
    )
    assert rows == []  # self-mentions are silenced


def test_description_mention_at_create_notifies(db):
    """Tagging someone in the description on create delivers a notification."""
    sarah = _user(db, "user_sarah_kim")
    issue_svc.create_issue(
        db, sarah,
        issue_svc.CreateIssueInput(
            project_key="SCRUM", issue_type="Task",
            summary="Body mention",
            description="please own this @priya_iyer",
        ),
    )
    rows = (
        db.query(Activity)
        .filter(Activity.action == "mentioned", Activity.to_value == "user_priya_iyer")
        .all()
    )
    assert len(rows) == 1
    assert rows[0].actor_id == "user_sarah_kim"


def test_description_mention_only_notifies_new_recipients_on_edit(db):
    sarah = _user(db, "user_sarah_kim")
    issue = issue_svc.create_issue(
        db, sarah,
        issue_svc.CreateIssueInput(
            project_key="SCRUM", issue_type="Task", summary="Edit mentions",
            description="cc @priya_iyer",
        ),
    )
    # Editing the description to add @marcus_obrien notifies marcus, NOT priya again.
    issue_svc.update_issue(
        db, sarah, issue.id,
        {"description": "cc @priya_iyer and @marcus_obrien"},
    )
    priya_rows = (
        db.query(Activity)
        .filter(Activity.action == "mentioned",
                Activity.to_value == "user_priya_iyer",
                Activity.issue_id == issue.id)
        .all()
    )
    marcus_rows = (
        db.query(Activity)
        .filter(Activity.action == "mentioned",
                Activity.to_value == "user_marcus_obrien",
                Activity.issue_id == issue.id)
        .all()
    )
    assert len(priya_rows) == 1, "priya should only be notified once, not on edit"
    assert len(marcus_rows) == 1, "marcus should be notified by the edit"


def test_my_mentions_rest_endpoint(client):
    # Sarah comments tagging Priya, then Priya fetches her mentions feed.
    headers_sarah = {"Authorization": "Bearer token_sarah_kim"}
    headers_priya = {"Authorization": "Bearer token_priya_iyer"}

    # Create an issue (SCRUM lead is sarah).
    r = client.post(
        "/api/issues",
        headers=headers_sarah,
        json={"project_key": "SCRUM", "summary": "Mention via REST", "issue_type": "Task"},
    )
    assert r.status_code == 201, r.text
    issue_id = r.json()["id"]

    r = client.post(
        f"/api/issues/{issue_id}/comments",
        headers=headers_sarah,
        json={"body": "Can you review this @priya_iyer?"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["mentions"] == ["user_priya_iyer"]

    r = client.get("/api/users/me/mentions", headers=headers_priya)
    assert r.status_code == 200
    feed = r.json()
    assert len(feed) >= 1
    latest = feed[0]
    assert latest["action"] == "mentioned"
    assert latest["to_value"] == "user_priya_iyer"
    assert latest["actor_id"] == "user_sarah_kim"
    assert latest["issue_id"] == issue_id
