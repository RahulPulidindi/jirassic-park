"""Tests for the Atlassian-compat REST surface at /rest/api/3/*.

The job of these tests is to verify the *shape* of our responses matches what
real Jira returns. We don't have a live Jira to diff against in CI, so we
encode the expected shape as Python types/keys per endpoint. When you capture
a fixture from a real Jira instance (`tests/fixtures/real_jira/*.json`),
extend these tests with a fixture-based shape-diff test.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.api.jira_compat.ids import account_id_for, numeric_id_for_issue
from app.models import Issue


def _auth(token: str = "token_sarah_kim") -> dict:
    return {"Authorization": f"Bearer {token}"}


def _shape(obj: Any) -> Any:
    """Strip values, keep structure + types. Used to assert key+nesting parity
    without depending on opaque values (timestamps, ids, generated URLs)."""
    if isinstance(obj, dict):
        return {k: _shape(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        if not obj:
            return []
        # Take the first element's shape as the representative.
        return [_shape(obj[0])]
    if obj is None:
        return "null"
    return type(obj).__name__


# =====================================================================
# Issue: get
# =====================================================================


def test_get_issue_shape_has_jira_envelope(client):
    r = client.get("/rest/api/3/issue/PLAT-60", headers=_auth())
    assert r.status_code == 200, r.text
    body = r.json()

    # Top-level Atlassian shape:
    assert set(body.keys()) >= {"id", "key", "self", "fields", "expand"}
    assert isinstance(body["id"], str) and body["id"].isdigit()
    assert body["key"] == "PLAT-60"
    assert body["self"].endswith(f"/rest/api/3/issue/{body['id']}")

    f = body["fields"]
    # Required Jira fields:
    for required in ("summary", "issuetype", "project", "status", "priority",
                     "assignee", "reporter", "creator", "description",
                     "labels", "created", "updated", "duedate", "resolution",
                     "components", "fixVersions", "subtasks", "issuelinks",
                     "parent", "comment", "worklog", "watches"):
        assert required in f, f"missing field: {required}"


def test_get_issue_user_refs_have_account_ids(client):
    r = client.get("/rest/api/3/issue/PLAT-60", headers=_auth())
    body = r.json()
    reporter = body["fields"]["reporter"]
    assert reporter is not None
    assert set(reporter.keys()) >= {"self", "accountId", "displayName", "active", "avatarUrls", "emailAddress"}
    # accountId is a 24-char hex string (Atlassian's shape).
    assert len(reporter["accountId"]) == 24
    assert all(c in "0123456789abcdef" for c in reporter["accountId"])
    # avatarUrls is a dict with the standard four sizes.
    assert set(reporter["avatarUrls"].keys()) == {"48x48", "32x32", "24x24", "16x16"}


def test_get_issue_status_has_category(client):
    r = client.get("/rest/api/3/issue/PLAT-60", headers=_auth())
    body = r.json()
    status = body["fields"]["status"]
    assert set(status.keys()) >= {"self", "id", "name", "statusCategory"}
    cat = status["statusCategory"]
    assert set(cat.keys()) >= {"id", "key", "name", "colorName"}
    assert cat["key"] in {"new", "indeterminate", "done"}


def test_get_issue_description_is_adf(client):
    r = client.get("/rest/api/3/issue/PLAT-60", headers=_auth())
    desc = r.json()["fields"]["description"]
    if desc is None:
        return
    assert desc["type"] == "doc"
    assert desc["version"] == 1
    assert isinstance(desc["content"], list)
    # Each content block should be a paragraph with text leaves.
    if desc["content"]:
        block = desc["content"][0]
        assert block["type"] == "paragraph"
        assert isinstance(block.get("content"), list)


def test_get_issue_comments_have_jira_shape(client):
    r = client.get("/rest/api/3/issue/PLAT-60", headers=_auth())
    comment_block = r.json()["fields"]["comment"]
    assert set(comment_block.keys()) >= {"comments", "self", "maxResults", "total", "startAt"}


def test_get_issue_accepts_numeric_id(client):
    r = client.get("/rest/api/3/issue/PLAT-60", headers=_auth())
    iid = r.json()["id"]
    # Same response shape regardless of how we reference it.
    r2 = client.get(f"/rest/api/3/issue/{iid}", headers=_auth())
    assert r2.status_code == 200
    assert r2.json()["key"] == "PLAT-60"


def test_get_issue_expand_changelog(client):
    r = client.get("/rest/api/3/issue/PLAT-60?expand=changelog", headers=_auth())
    body = r.json()
    assert "changelog" in body
    cl = body["changelog"]
    assert set(cl.keys()) >= {"startAt", "maxResults", "total", "histories"}


# =====================================================================
# Error envelope
# =====================================================================


def test_unknown_issue_returns_jira_envelope_404(client):
    r = client.get("/rest/api/3/issue/NOPE-9999", headers=_auth())
    assert r.status_code == 404
    body = r.json()
    # Real Jira shape:
    assert set(body.keys()) == {"errorMessages", "errors"}
    assert isinstance(body["errorMessages"], list)
    assert isinstance(body["errors"], dict)
    # Soft-404 wording — agents pattern-match on this.
    assert any("does not exist or you do not have permission" in m for m in body["errorMessages"])


def test_missing_auth_returns_jira_envelope_401(client):
    r = client.get("/rest/api/3/issue/PLAT-60")  # no Authorization header
    assert r.status_code == 401
    body = r.json()
    assert set(body.keys()) == {"errorMessages", "errors"}


def test_legacy_api_keeps_detail_shape(client):
    """The /api/* surface used by the React frontend keeps {detail: ...}."""
    r = client.get("/api/issues/NOPE-9999", headers=_auth())
    assert r.status_code == 404
    body = r.json()
    assert "detail" in body
    assert "errorMessages" not in body


# =====================================================================
# Search
# =====================================================================


def test_search_get_pagination_shape(client):
    r = client.get(
        "/rest/api/3/search",
        params={"jql": "project = PLAT", "startAt": 0, "maxResults": 5},
        headers=_auth(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) >= {"startAt", "maxResults", "total", "isLast", "issues", "expand"}
    assert body["startAt"] == 0
    assert body["maxResults"] == 5
    assert len(body["issues"]) <= 5
    # Each issue is a full Jira issue object.
    for issue in body["issues"]:
        assert "id" in issue and "key" in issue and "fields" in issue


def test_search_post_jql(client):
    r = client.post(
        "/rest/api/3/search",
        json={"jql": "project = PLAT", "startAt": 0, "maxResults": 3, "fields": ["summary", "status"]},
        headers=_auth(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    for issue in body["issues"]:
        # `fields` restricted to what we asked for.
        assert set(issue["fields"].keys()) <= {"summary", "status"}


# =====================================================================
# Transitions
# =====================================================================


def test_list_transitions_shape(client):
    r = client.get("/rest/api/3/issue/PLAT-1/transitions", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert "transitions" in body
    if body["transitions"]:
        t = body["transitions"][0]
        for k in ("id", "name", "to", "hasScreen", "isGlobal", "isAvailable"):
            assert k in t
        for k in ("id", "name", "statusCategory"):
            assert k in t["to"]


def test_do_transition_by_name(client, db):
    # Pick a non-Epic issue (Epic-to-Done is guard-blocked when children
    # aren't all done) and transition to the first non-Done target so this
    # test is independent of seed-specific guard state.
    transitions_resp = client.get("/rest/api/3/issue/PLAT-6/transitions", headers=_auth())
    available = transitions_resp.json()["transitions"]
    if not available:
        pytest.skip("PLAT-6 has no transitions available in seed state.")
    # Find any transition that won't trip a guard (skip done-category).
    non_done = [t for t in available if t["to"]["statusCategory"]["key"] != "done"]
    target = non_done[0] if non_done else available[0]
    target_name = target["to"]["name"]
    r = client.post(
        "/rest/api/3/issue/PLAT-6/transitions",
        json={"transition": {"name": target_name}},
        headers=_auth(),
    )
    assert r.status_code == 204, r.text
    after = client.get("/rest/api/3/issue/PLAT-6", headers=_auth()).json()
    assert after["fields"]["status"]["name"] == target_name


# =====================================================================
# Comments
# =====================================================================


def test_add_comment_returns_jira_shape(client):
    r = client.post(
        "/rest/api/3/issue/PLAT-60/comment",
        json={"body": "Test comment via Jira-compat API."},
        headers=_auth(),
    )
    assert r.status_code == 201, r.text
    c = r.json()
    for k in ("self", "id", "author", "body", "created", "updated"):
        assert k in c
    assert c["body"]["type"] == "doc"  # ADF-wrapped
    assert c["author"]["accountId"]


def test_list_comments_pagination_shape(client):
    r = client.get("/rest/api/3/issue/PLAT-60/comment", headers=_auth())
    body = r.json()
    assert set(body.keys()) >= {"startAt", "maxResults", "total", "comments"}


# =====================================================================
# Watchers
# =====================================================================


def test_watchers_endpoint_shape(client):
    r = client.get("/rest/api/3/issue/PLAT-60/watchers", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"self", "isWatching", "watchCount", "watchers"}
    assert isinstance(body["watchers"], list)


def test_add_watcher_then_list(client):
    # Watch as the authenticated user (Sarah).
    r = client.post(
        "/rest/api/3/issue/PLAT-60/watchers",
        json="",  # empty body == watch myself
        headers=_auth(),
    )
    assert r.status_code == 204
    watchers = client.get("/rest/api/3/issue/PLAT-60/watchers", headers=_auth()).json()
    assert watchers["isWatching"] is True


# =====================================================================
# Users / myself / metadata
# =====================================================================


def test_myself_returns_jira_user_shape(client):
    r = client.get("/rest/api/3/myself", headers=_auth())
    body = r.json()
    assert set(body.keys()) >= {"self", "accountId", "displayName", "emailAddress", "active", "avatarUrls", "timeZone"}


def test_get_user_by_accountid(client, db):
    from app.models import User
    sarah = db.query(User).filter(User.id == "user_sarah_kim").one()
    aid = account_id_for(sarah.id)
    r = client.get(f"/rest/api/3/user?accountId={aid}", headers=_auth())
    assert r.status_code == 200
    assert r.json()["displayName"] in ("Sarah", "Sarah Kim")


def test_list_priorities(client):
    r = client.get("/rest/api/3/priority", headers=_auth())
    body = r.json()
    assert isinstance(body, list)
    assert {b["name"] for b in body} == {"Highest", "High", "Medium", "Low", "Lowest"}
    # Atlassian uses fixed 1..5 ids for these.
    by_name = {b["name"]: b for b in body}
    assert by_name["Highest"]["id"] == "1"
    assert by_name["Medium"]["id"] == "3"


def test_list_issuetypes(client):
    r = client.get("/rest/api/3/issuetype", headers=_auth())
    body = r.json()
    names = {b["name"] for b in body}
    assert {"Bug", "Story", "Task", "Epic", "Subtask"} <= names


def test_list_statuses(client):
    r = client.get("/rest/api/3/status", headers=_auth())
    body = r.json()
    names = {b["name"] for b in body}
    assert {"To Do", "In Progress", "Done"} <= names


def test_server_info(client):
    r = client.get("/rest/api/3/serverInfo", headers=_auth())
    body = r.json()
    for k in ("baseUrl", "version", "versionNumbers", "deploymentType", "buildNumber", "serverTime"):
        assert k in body


def test_field_list_has_well_known_customfields(client):
    r = client.get("/rest/api/3/field", headers=_auth())
    body = r.json()
    ids = {f["id"] for f in body}
    assert "customfield_10016" in ids  # Story points
    assert "customfield_10020" in ids  # Sprint
    assert "customfield_10014" in ids  # Epic link


# =====================================================================
# Project
# =====================================================================


def test_get_project_shape(client):
    r = client.get("/rest/api/3/project/PLAT", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    for k in ("id", "key", "name", "projectTypeKey", "lead", "issueTypes",
              "components", "versions", "style", "isPrivate"):
        assert k in body


def test_list_projects(client):
    r = client.get("/rest/api/3/project", headers=_auth())
    body = r.json()
    assert isinstance(body, list)
    keys = {p["key"] for p in body}
    assert "PLAT" in keys


# =====================================================================
# Issue create / edit via Jira shape
# =====================================================================


def test_create_issue_jira_shape(client):
    r = client.post(
        "/rest/api/3/issue",
        json={
            "fields": {
                "project": {"key": "PLAT"},
                "issuetype": {"name": "Task"},
                "summary": "Created via Jira-compat shape",
                "description": {
                    "type": "doc", "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Body here."}]}],
                },
                "priority": {"name": "High"},
                "labels": ["from-jira-compat"],
            },
        },
        headers=_auth(),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body.keys()) == {"id", "key", "self"}
    assert body["key"].startswith("PLAT-")
    # Verify it persisted with the right shape.
    after = client.get(f"/rest/api/3/issue/{body['key']}", headers=_auth()).json()
    assert after["fields"]["summary"] == "Created via Jira-compat shape"
    assert after["fields"]["priority"]["name"] == "High"
    assert "from-jira-compat" in after["fields"]["labels"]


def test_edit_issue_via_put(client, db):
    issue = db.query(Issue).filter(Issue.id == "PLAT-60").one()
    r = client.put(
        "/rest/api/3/issue/PLAT-60",
        json={"fields": {"summary": "Updated via PUT", "priority": {"name": "Low"}}},
        headers=_auth(),
    )
    assert r.status_code == 204
    after = client.get("/rest/api/3/issue/PLAT-60", headers=_auth()).json()
    assert after["fields"]["summary"] == "Updated via PUT"
    assert after["fields"]["priority"]["name"] == "Low"


# =====================================================================
# MCP Atlassian-named aliases share underlying state with REST
# =====================================================================


def test_mcp_atlassian_alias_get_jira_issue(mcp_call):
    """Verify the camelCase alias returns the same Jira-shape body."""
    out = mcp_call("getJiraIssue", {"issueIdOrKey": "PLAT-60", "auth_token": "token_sarah_kim"})
    assert out["key"] == "PLAT-60"
    assert "fields" in out
    assert out["fields"]["status"]["statusCategory"]["key"] in {"new", "indeterminate", "done"}


def test_mcp_atlassian_alias_transition(mcp_call, client):
    transitions = mcp_call("getJiraIssueTransitions", {"issueIdOrKey": "PLAT-6", "auth_token": "token_sarah_kim"})
    assert "transitions" in transitions
    if not transitions["transitions"]:
        pytest.skip("No transitions for PLAT-6.")
    non_done = [t for t in transitions["transitions"] if t["to"]["statusCategory"]["key"] != "done"]
    target = non_done[0] if non_done else transitions["transitions"][0]
    target_name = target["to"]["name"]
    result = mcp_call("transitionJiraIssue", {
        "issueIdOrKey": "PLAT-6",
        "transition": {"name": target_name},
        "auth_token": "token_sarah_kim",
    })
    assert result["key"] == "PLAT-6"
    # And REST sees the same updated state.
    after = client.get("/rest/api/3/issue/PLAT-6", headers=_auth()).json()
    assert after["fields"]["status"]["name"] == target_name
