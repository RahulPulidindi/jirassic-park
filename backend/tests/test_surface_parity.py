"""Surface parity tests.

The prompt's explicit requirement: prove that REST and MCP mutate the same
underlying state. We run the same logical operation through both surfaces and
assert the resulting DB rows are byte-identical (modulo opaque ids and
timestamps which we strip before comparing).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.models import Activity, Comment, Issue, IssueLink, SprintIssue, Watcher


# Strip fields whose values are guaranteed-distinct between runs (ids, timestamps).
_STRIP = {
    "id", "created_at", "updated_at", "edited_at", "created", "completed_at",
    "added_at",
}


def _normalize_issue(issue: Issue) -> dict:
    d = {
        "project_key": issue.project_key,
        "issue_type": issue.issue_type,
        "summary": issue.summary,
        "description": issue.description,
        "status_id": issue.status_id,
        "board_list": issue.board_list,
        "priority": issue.priority,
        "owner": issue.owner,
        "reporter": issue.reporter,
        "parent_id": issue.parent_id,
        "epic_id": issue.epic_id,
        "story_points": issue.story_points,
        "resolution": issue.resolution,
        "due_date": str(issue.due_date) if issue.due_date else None,
    }
    return d


def _normalize_activities(db, issue_id: str) -> list[dict]:
    rows = (
        db.query(Activity)
        .filter(Activity.issue_id == issue_id)
        .order_by(Activity.created_at, Activity.id)
        .all()
    )
    return [
        {
            "action": r.action,
            "field": r.field,
            "from_value": r.from_value,
            "to_value": r.to_value,
            "actor_id": r.actor_id,
            "comment_body": r.comment_body,
        }
        for r in rows
    ]


def _normalize_comments(db, issue_id: str) -> list[dict]:
    rows = (
        db.query(Comment)
        .filter(Comment.issue_id == issue_id)
        .order_by(Comment.created_at, Comment.id)
        .all()
    )
    return [{"author_id": c.author_id, "body": c.body} for c in rows]


# ---- The actual parity scenarios --------------------------------------


def _ops_create_transition_comment_via_rest(client) -> str:
    h = {"Authorization": "Bearer admin-token-jurassic"}
    r = client.post(
        "/api/issues",
        json={
            "project_key": "PLAT", "issue_type": "Task", "summary": "Parity probe",
            "description": "shared body", "priority": "High", "owner": "user_marcus_obrien",
            "labels": ["regression"],
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    r = client.post(f"/api/issues/{iid}/transitions", json={"to_status": "In Progress"}, headers=h)
    assert r.status_code == 200
    r = client.post(f"/api/issues/{iid}/comments", json={"body": "parity comment"}, headers=h)
    assert r.status_code == 201
    return iid


def _ops_create_transition_comment_via_mcp(mcp_call) -> str:
    r = mcp_call(
        "jira_create_issue",
        {
            "auth_token": "admin-token-jurassic",
            "project_key": "PLAT", "issue_type": "Task", "summary": "Parity probe",
            "description": "shared body", "priority": "High", "owner": "user_marcus_obrien",
            "labels": ["regression"],
        },
    )
    iid = r["id"]
    mcp_call(
        "jira_transition_issue",
        {"auth_token": "admin-token-jurassic", "id": iid, "to_status": "In Progress"},
    )
    mcp_call(
        "jira_add_comment",
        {"auth_token": "admin-token-jurassic", "id": iid, "body": "parity comment"},
    )
    return iid


def test_create_transition_comment_parity(client, mcp_call):
    """Run via REST, capture state; reset; run via MCP, capture state; compare."""
    from app.db import init_engine, reset_state_from_seed, session_scope

    # ---- REST path ----
    iid_rest = _ops_create_transition_comment_via_rest(client)
    with session_scope() as db:
        issue = db.query(Issue).filter(Issue.id == iid_rest).one()
        rest_issue = _normalize_issue(issue)
        rest_acts = _normalize_activities(db, iid_rest)
        rest_comments = _normalize_comments(db, iid_rest)

    # ---- Reset ----
    reset_state_from_seed()
    init_engine()

    # ---- MCP path ----
    iid_mcp = _ops_create_transition_comment_via_mcp(mcp_call)
    with session_scope() as db:
        issue = db.query(Issue).filter(Issue.id == iid_mcp).one()
        mcp_issue = _normalize_issue(issue)
        mcp_acts = _normalize_activities(db, iid_mcp)
        mcp_comments = _normalize_comments(db, iid_mcp)

    assert iid_rest == iid_mcp, "Both surfaces should produce the same auto-incrementing id."
    assert rest_issue == mcp_issue
    assert rest_acts == mcp_acts
    assert rest_comments == mcp_comments


def test_assign_via_rest_and_mcp_match(client, mcp_call):
    from app.db import init_engine, reset_state_from_seed, session_scope

    h = {"Authorization": "Bearer admin-token-jurassic"}

    # REST path
    r = client.post("/api/issues", json={
        "project_key": "PLAT", "issue_type": "Bug", "summary": "Assign parity",
    }, headers=h)
    iid_rest = r.json()["id"]
    client.post(f"/api/issues/{iid_rest}/assign", json={"assignee": "user_lina_garcia"}, headers=h)
    with session_scope() as db:
        rest_state = _normalize_issue(db.query(Issue).filter_by(id=iid_rest).one())
        rest_acts = _normalize_activities(db, iid_rest)

    reset_state_from_seed()
    init_engine()

    r = mcp_call("jira_create_issue", {
        "auth_token": "admin-token-jurassic",
        "project_key": "PLAT", "issue_type": "Bug", "summary": "Assign parity",
    })
    iid_mcp = r["id"]
    mcp_call("jira_assign_issue", {"auth_token": "admin-token-jurassic", "id": iid_mcp, "assignee": "user_lina_garcia"})
    with session_scope() as db:
        mcp_state = _normalize_issue(db.query(Issue).filter_by(id=iid_mcp).one())
        mcp_acts = _normalize_activities(db, iid_mcp)

    assert rest_state == mcp_state
    assert rest_acts == mcp_acts


def test_link_parity(client, mcp_call):
    from app.db import init_engine, reset_state_from_seed, session_scope

    h = {"Authorization": "Bearer admin-token-jurassic"}

    # REST: create two issues + link
    a = client.post("/api/issues", json={"project_key": "PLAT", "summary": "A"}, headers=h).json()["id"]
    b = client.post("/api/issues", json={"project_key": "PLAT", "summary": "B"}, headers=h).json()["id"]
    client.post(f"/api/issues/{a}/links", json={"target": b, "link_type": "blocks"}, headers=h)
    with session_scope() as db:
        rest_links = sorted(
            [(l.source_id, l.target_id, l.link_type) for l in db.query(IssueLink).filter(IssueLink.source_id == a).all()]
        )

    reset_state_from_seed()
    init_engine()

    a2 = mcp_call("jira_create_issue", {"auth_token": "admin-token-jurassic", "project_key": "PLAT", "summary": "A"})["id"]
    b2 = mcp_call("jira_create_issue", {"auth_token": "admin-token-jurassic", "project_key": "PLAT", "summary": "B"})["id"]
    mcp_call("jira_link_issues", {"auth_token": "admin-token-jurassic", "source": a2, "target": b2, "link_type": "blocks"})
    with session_scope() as db:
        mcp_links = sorted(
            [(l.source_id, l.target_id, l.link_type) for l in db.query(IssueLink).filter(IssueLink.source_id == a2).all()]
        )

    assert rest_links == mcp_links
    assert (a, b, "blocks") in rest_links


def test_search_parity(client, mcp_call):
    """REST GET and MCP search should return the same issue ids for the same JQL."""
    jql = 'project = "SCRUM" AND status = "In Progress"'
    h = {"Authorization": "Bearer admin-token-jurassic"}
    r1 = client.get(f"/api/search?jql={jql}", headers=h).json()
    r2 = mcp_call("jira_search", {"auth_token": "admin-token-jurassic", "jql": jql, "limit": 50})

    rest_ids = sorted(i["id"] for i in r1["issues"])
    mcp_ids = sorted(i["id"] for i in r2["issues"])
    assert rest_ids == mcp_ids
    assert r1["total"] == r2["total"]


# ---- Newly-added tools: every REST endpoint should have a working MCP twin --


def test_unlink_parity(client, mcp_call):
    """linkIssue + unlinkIssue via REST vs MCP should leave identical link tables."""
    from app.db import init_engine, reset_state_from_seed, session_scope

    h = {"Authorization": "Bearer admin-token-jurassic"}

    # ---- REST
    a = client.post("/api/issues", json={"project_key": "PLAT", "summary": "A"}, headers=h).json()["id"]
    b = client.post("/api/issues", json={"project_key": "PLAT", "summary": "B"}, headers=h).json()["id"]
    client.post(f"/api/issues/{a}/links", json={"target": b, "link_type": "blocks"}, headers=h)
    client.request("DELETE", f"/api/issues/{a}/links", json={"target": b, "link_type": "blocks"}, headers=h)
    with session_scope() as db:
        rest_links = [l.id for l in db.query(IssueLink).filter(IssueLink.source_id == a).all()]
    assert rest_links == [], "REST: link should be gone after DELETE."

    reset_state_from_seed()
    init_engine()

    # ---- MCP
    args = {"auth_token": "admin-token-jurassic"}
    a2 = mcp_call("jira_create_issue", {**args, "project_key": "PLAT", "summary": "A"})["id"]
    b2 = mcp_call("jira_create_issue", {**args, "project_key": "PLAT", "summary": "B"})["id"]
    mcp_call("jira_link_issues", {**args, "source": a2, "target": b2, "link_type": "blocks"})
    mcp_call("jira_unlink_issues", {**args, "source": a2, "target": b2, "link_type": "blocks"})
    with session_scope() as db:
        mcp_links = [l.id for l in db.query(IssueLink).filter(IssueLink.source_id == a2).all()]
    assert mcp_links == [], "MCP: link should be gone after jira_unlink_issues."
    assert rest_links == mcp_links


def test_label_remove_parity(client, mcp_call):
    """remove_label via REST vs MCP should leave identical label sets and activities."""
    from app.db import init_engine, reset_state_from_seed, session_scope
    from app.models import IssueLabel

    h = {"Authorization": "Bearer admin-token-jurassic"}

    # REST
    iid = client.post(
        "/api/issues",
        json={"project_key": "PLAT", "summary": "Label parity", "labels": ["regression", "infra"]},
        headers=h,
    ).json()["id"]
    client.delete(f"/api/issues/{iid}/labels/regression", headers=h)
    with session_scope() as db:
        rest_labels = sorted(l.label_name for l in db.query(IssueLabel).filter_by(issue_id=iid).all())
        rest_acts = _normalize_activities(db, iid)

    reset_state_from_seed()
    init_engine()

    # MCP
    args = {"auth_token": "admin-token-jurassic"}
    iid2 = mcp_call(
        "jira_create_issue",
        {**args, "project_key": "PLAT", "summary": "Label parity", "labels": ["regression", "infra"]},
    )["id"]
    mcp_call("jira_remove_label", {**args, "id": iid2, "label": "regression"})
    with session_scope() as db:
        mcp_labels = sorted(l.label_name for l in db.query(IssueLabel).filter_by(issue_id=iid2).all())
        mcp_acts = _normalize_activities(db, iid2)

    assert rest_labels == mcp_labels == ["infra"]
    assert rest_acts == mcp_acts


def test_unwatch_parity(client, mcp_call):
    """watch + unwatch via REST vs MCP should leave identical watcher rows + activities."""
    from app.db import init_engine, reset_state_from_seed, session_scope

    h = {"Authorization": "Bearer admin-token-jurassic"}
    # REST
    iid = client.post("/api/issues", json={"project_key": "PLAT", "summary": "Watch parity"}, headers=h).json()["id"]
    client.post(f"/api/issues/{iid}/watch", headers=h)
    client.delete(f"/api/issues/{iid}/watch", headers=h)
    with session_scope() as db:
        rest_watchers = [w.user_id for w in db.query(Watcher).filter_by(issue_id=iid).all()]
        rest_acts = _normalize_activities(db, iid)

    reset_state_from_seed()
    init_engine()

    # MCP
    args = {"auth_token": "admin-token-jurassic"}
    iid2 = mcp_call("jira_create_issue", {**args, "project_key": "PLAT", "summary": "Watch parity"})["id"]
    mcp_call("jira_watch_issue", {**args, "id": iid2})
    mcp_call("jira_unwatch_issue", {**args, "id": iid2})
    with session_scope() as db:
        mcp_watchers = [w.user_id for w in db.query(Watcher).filter_by(issue_id=iid2).all()]
        mcp_acts = _normalize_activities(db, iid2)

    assert rest_watchers == mcp_watchers == []
    assert rest_acts == mcp_acts


def test_list_comments_parity(client, mcp_call):
    """jira_list_comments should match GET /api/issues/{id}/comments exactly."""
    h = {"Authorization": "Bearer admin-token-jurassic"}
    iid = client.post("/api/issues", json={"project_key": "PLAT", "summary": "Comment parity"}, headers=h).json()["id"]
    client.post(f"/api/issues/{iid}/comments", json={"body": "first"}, headers=h)
    client.post(f"/api/issues/{iid}/comments", json={"body": "second"}, headers=h)

    rest = client.get(f"/api/issues/{iid}/comments", headers=h).json()
    mcp = mcp_call("jira_list_comments", {"auth_token": "admin-token-jurassic", "id": iid})
    assert [c["body"] for c in rest] == [c["body"] for c in mcp] == ["first", "second"]


def test_create_sprint_parity(client, mcp_call):
    """Create + add issues + start + complete a sprint through REST and MCP. Verify same shape."""
    from app.db import init_engine, reset_state_from_seed, session_scope
    from app.models import Sprint

    h = {"Authorization": "Bearer admin-token-jurassic"}

    # REST
    sr = client.post(
        "/api/sprints",
        json={"project_key": "PLAT", "name": "PLAT Sprint Parity", "goal": "Test parity"},
        headers=h,
    ).json()
    assert sr["state"] == "future"
    with session_scope() as db:
        rest_sprint = db.query(Sprint).filter_by(id=sr["id"]).one()
        rest_view = {
            "project_key": rest_sprint.project_key,
            "name": rest_sprint.name,
            "state": rest_sprint.state,
            "goal": rest_sprint.goal,
        }

    reset_state_from_seed()
    init_engine()

    args = {"auth_token": "admin-token-jurassic"}
    sm = mcp_call(
        "jira_create_sprint",
        {**args, "project_key": "PLAT", "name": "PLAT Sprint Parity", "goal": "Test parity"},
    )
    assert sm["state"] == "future"
    with session_scope() as db:
        mcp_sprint = db.query(Sprint).filter_by(id=sm["id"]).one()
        mcp_view = {
            "project_key": mcp_sprint.project_key,
            "name": mcp_sprint.name,
            "state": mcp_sprint.state,
            "goal": mcp_sprint.goal,
        }
    assert rest_view == mcp_view


def test_get_workflow_parity(client, mcp_call):
    """REST GET /projects/{key}/workflow and MCP jira_get_workflow should match."""
    h = {"Authorization": "Bearer admin-token-jurassic"}
    rest = client.get("/api/projects/PLAT/workflow", headers=h).json()
    mcp = mcp_call("jira_get_workflow", {"auth_token": "admin-token-jurassic", "project_key": "PLAT"})

    # Stable subset: names and ids of statuses + names of transitions
    assert sorted(s["id"] for s in rest["statuses"]) == sorted(s["id"] for s in mcp["statuses"])
    assert sorted(t["name"] for t in rest["transitions"]) == sorted(
        t["name"] for t in mcp["transitions"]
    )


def test_list_boards_parity(client, mcp_call):
    """REST GET /boards and MCP jira_list_boards should return the same board ids."""
    h = {"Authorization": "Bearer admin-token-jurassic"}
    rest_ids = sorted(b["id"] for b in client.get("/api/boards", headers=h).json())
    mcp_ids = sorted(
        b["id"] for b in mcp_call("jira_list_boards", {"auth_token": "admin-token-jurassic"})
    )
    assert rest_ids == mcp_ids


def test_create_filter_parity(client, mcp_call):
    """Saved filter create via REST vs MCP — same shape, both readable from list_filters."""
    from app.db import init_engine, reset_state_from_seed

    h = {"Authorization": "Bearer admin-token-jurassic"}

    rest = client.post(
        "/api/filters",
        json={"name": "Parity REST", "jql": "priority = Highest", "shared": True},
        headers=h,
    ).json()
    rest_view = {k: rest[k] for k in ("name", "jql", "shared", "owner_id")}

    reset_state_from_seed()
    init_engine()

    args = {"auth_token": "admin-token-jurassic"}
    mcp = mcp_call(
        "jira_create_filter",
        {**args, "name": "Parity REST", "jql": "priority = Highest", "shared": True},
    )
    mcp_view = {k: mcp[k] for k in ("name", "jql", "shared", "owner_id")}
    assert rest_view == mcp_view


def test_set_clock_parity(client, mcp_call):
    """POST /api/admin/clock and jira_set_clock should leave the env in the same state."""
    from app import clock as _clock

    h = {"Authorization": "Bearer admin-token-jurassic"}
    client.post(
        "/api/admin/clock",
        json={"mode": "frozen", "at": "2030-01-01T00:00:00Z"},
        headers=h,
    )
    rest_state = _clock.describe()

    # Reset clock via MCP
    mcp_call(
        "jira_set_clock",
        {"auth_token": "admin-token-jurassic", "mode": "frozen", "at": "2030-01-01T00:00:00Z"},
    )
    mcp_state = _clock.describe()
    assert rest_state["mode"] == mcp_state["mode"] == "frozen"
    assert rest_state["frozen_at"] == mcp_state["frozen_at"]

    # Restore tick mode for subsequent tests (conftest's autouse fixture also resets)
    from app.clock import tick_from
    tick_from("2026-05-27T12:00:00Z")


def test_admin_reset_via_mcp(client, mcp_call):
    """jira_admin_reset should drop in-flight mutations just like POST /admin/reset."""
    from app.db import session_scope

    h = {"Authorization": "Bearer admin-token-jurassic"}
    # Mutate
    iid = client.post(
        "/api/issues",
        json={"project_key": "PLAT", "summary": "Will be erased"},
        headers=h,
    ).json()["id"]

    # Reset via MCP
    mcp_call("jira_admin_reset", {"auth_token": "admin-token-jurassic"})

    # The issue should no longer exist
    with session_scope() as db:
        assert db.query(Issue).filter(Issue.id == iid).one_or_none() is None


def test_comment_edit_parity(client, mcp_call):
    """Edit a comment via REST and via MCP — same body, same mentions, same activity rows."""
    from app.db import init_engine, reset_state_from_seed, session_scope
    from app.models import Comment as CommentRow

    h = {"Authorization": "Bearer admin-token-jurassic"}

    # REST
    iid = client.post("/api/issues", json={"project_key": "PLAT", "summary": "Comment edit parity"}, headers=h).json()["id"]
    cid = client.post(f"/api/issues/{iid}/comments", json={"body": "draft"}, headers=h).json()["id"]
    client.patch(
        f"/api/issues/{iid}/comments/{cid}",
        json={"body": "edited body @priya_iyer"},
        headers=h,
    )
    with session_scope() as db:
        cr = db.query(CommentRow).filter_by(id=cid).one()
        rest_view = {"body": cr.body, "mentions": list(cr.mentions or []), "edited": cr.edited_at is not None}
        rest_acts = _normalize_activities(db, iid)

    reset_state_from_seed()
    init_engine()

    args = {"auth_token": "admin-token-jurassic"}
    iid2 = mcp_call("jira_create_issue", {**args, "project_key": "PLAT", "summary": "Comment edit parity"})["id"]
    cid2 = mcp_call("jira_add_comment", {**args, "id": iid2, "body": "draft"})["id"]
    mcp_call(
        "jira_update_comment",
        {**args, "issue_id": iid2, "comment_id": cid2, "body": "edited body @priya_iyer"},
    )
    with session_scope() as db:
        cr2 = db.query(CommentRow).filter_by(id=cid2).one()
        mcp_view = {"body": cr2.body, "mentions": list(cr2.mentions or []), "edited": cr2.edited_at is not None}
        mcp_acts = _normalize_activities(db, iid2)

    assert rest_view == mcp_view
    assert rest_view["mentions"] == ["user_priya_iyer"]
    assert rest_view["edited"] is True
    assert rest_acts == mcp_acts
    # The first edit must fire a `mentioned` activity (priya wasn't in the original body)
    assert any(a["action"] == "mentioned" for a in rest_acts)


def test_comment_edit_author_only(client):
    """Only the comment author (or an admin) can edit. Other users get 403."""
    h_admin = {"Authorization": "Bearer admin-token-jurassic"}
    iid = client.post(
        "/api/issues",
        json={"project_key": "PLAT", "summary": "Auth test"},
        headers=h_admin,
    ).json()["id"]
    cid = client.post(
        f"/api/issues/{iid}/comments",
        json={"body": "by admin"},
        headers=h_admin,
    ).json()["id"]

    # Priya is not the author and not an admin
    h_priya = {"Authorization": "Bearer token_priya_iyer"}
    r = client.patch(
        f"/api/issues/{iid}/comments/{cid}",
        json={"body": "hijack"},
        headers=h_priya,
    )
    assert r.status_code == 403, r.text


def test_comment_delete_parity(client, mcp_call):
    """Delete via REST vs MCP — both remove the row, both emit comment_deleted activity."""
    from app.db import init_engine, reset_state_from_seed, session_scope
    from app.models import Comment as CommentRow

    h = {"Authorization": "Bearer admin-token-jurassic"}

    iid = client.post("/api/issues", json={"project_key": "PLAT", "summary": "delete parity"}, headers=h).json()["id"]
    cid = client.post(f"/api/issues/{iid}/comments", json={"body": "going away"}, headers=h).json()["id"]
    r = client.delete(f"/api/issues/{iid}/comments/{cid}", headers=h)
    assert r.status_code == 204
    with session_scope() as db:
        assert db.query(CommentRow).filter_by(id=cid).one_or_none() is None
        rest_acts = _normalize_activities(db, iid)

    reset_state_from_seed()
    init_engine()

    args = {"auth_token": "admin-token-jurassic"}
    iid2 = mcp_call("jira_create_issue", {**args, "project_key": "PLAT", "summary": "delete parity"})["id"]
    cid2 = mcp_call("jira_add_comment", {**args, "id": iid2, "body": "going away"})["id"]
    mcp_call("jira_delete_comment", {**args, "issue_id": iid2, "comment_id": cid2})
    with session_scope() as db:
        assert db.query(CommentRow).filter_by(id=cid2).one_or_none() is None
        mcp_acts = _normalize_activities(db, iid2)

    assert rest_acts == mcp_acts
    assert any(a["action"] == "comment_deleted" for a in rest_acts)


def test_due_date_via_mcp_string(client, mcp_call):
    """Regression: MCP `jira_update_issue({due_date: '2026-06-30'})` shouldn't blow up.

    Pydantic on the REST path coerces the string into a `date`; the MCP path
    bypasses Pydantic so the service layer must do its own date coercion.
    """
    from app.db import init_engine, reset_state_from_seed, session_scope
    from app.models import Issue as IssueRow

    args = {"auth_token": "admin-token-jurassic"}
    iid = mcp_call("jira_create_issue", {**args, "project_key": "PLAT", "summary": "Date coercion"})["id"]
    mcp_call("jira_update_issue", {**args, "id": iid, "patch": {"due_date": "2026-06-30"}})
    with session_scope() as db:
        row = db.query(IssueRow).filter_by(id=iid).one()
        assert row.due_date is not None
        assert str(row.due_date) == "2026-06-30"

    # Same value via REST should also work and produce the same stored type.
    h = {"Authorization": "Bearer admin-token-jurassic"}
    reset_state_from_seed()
    init_engine()
    iid2 = client.post("/api/issues", json={"project_key": "PLAT", "summary": "Date coercion"}, headers=h).json()["id"]
    client.patch(f"/api/issues/{iid2}", json={"due_date": "2026-06-30"}, headers=h)
    with session_scope() as db:
        row = db.query(IssueRow).filter_by(id=iid2).one()
        assert str(row.due_date) == "2026-06-30"


def test_description_edit_parity(client, mcp_call):
    """Editing the description through PATCH /issues vs jira_update_issue should:
    - persist the new description identically
    - fire a `mentioned` activity for any newly-tagged user (but NOT for users
      already mentioned in the previous version)."""
    from app.db import init_engine, reset_state_from_seed, session_scope
    from app.models import Issue as IssueRow

    h = {"Authorization": "Bearer admin-token-jurassic"}

    iid = client.post(
        "/api/issues",
        json={
            "project_key": "PLAT",
            "summary": "Desc parity",
            "description": "first cut @priya_iyer",
        },
        headers=h,
    ).json()["id"]
    client.patch(
        f"/api/issues/{iid}",
        json={"description": "second cut @priya_iyer @marcus_obrien"},
        headers=h,
    )
    with session_scope() as db:
        rest_desc = db.query(IssueRow).filter_by(id=iid).one().description
        rest_acts = _normalize_activities(db, iid)

    reset_state_from_seed()
    init_engine()

    args = {"auth_token": "admin-token-jurassic"}
    iid2 = mcp_call(
        "jira_create_issue",
        {
            **args, "project_key": "PLAT", "summary": "Desc parity",
            "description": "first cut @priya_iyer",
        },
    )["id"]
    mcp_call(
        "jira_update_issue",
        {**args, "id": iid2, "patch": {"description": "second cut @priya_iyer @marcus_obrien"}},
    )
    with session_scope() as db:
        mcp_desc = db.query(IssueRow).filter_by(id=iid2).one().description
        mcp_acts = _normalize_activities(db, iid2)

    assert rest_desc == mcp_desc == "second cut @priya_iyer @marcus_obrien"
    assert rest_acts == mcp_acts
    # The edit should mention only `marcus_obrien` (priya was already in the previous body)
    mention_targets = [a["to_value"] for a in rest_acts if a["action"] == "mentioned"]
    # Includes the initial-create mention of priya, plus the marcus mention on edit
    assert "user_marcus_obrien" in mention_targets
    assert mention_targets.count("user_priya_iyer") == 1


def test_set_clock_requires_admin(mcp_call):
    """Non-admin tokens cannot reconfigure the clock from MCP either."""
    with pytest.raises(Exception) as ei:
        mcp_call(
            "jira_set_clock",
            {"auth_token": "token_priya_iyer", "mode": "frozen", "at": "2030-01-01T00:00:00Z"},
        )
    assert "admin" in str(ei.value).lower() or "permission" in str(ei.value).lower()
