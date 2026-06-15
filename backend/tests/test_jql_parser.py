"""JQL parser and evaluator tests."""

from __future__ import annotations

import pytest

from app.models import Issue, User
from app.services.search import parse_jql, search


def _sarah(db):
    return db.query(User).filter(User.id == "user_sarah_kim").one()


def _user(db, uid):
    return db.query(User).filter(User.id == uid).one()


@pytest.mark.parametrize(
    "jql",
    [
        "project = SCRUM",
        'project = "SCRUM"',
        'status = "In Progress"',
        "priority in (Highest, High)",
        "assignee = currentUser()",
        "assignee = unassigned()",
        'labels = "infra"',
        "labels in (ios, android)",
        'text ~ "login"',
        "created >= -7d",
        "updated <= -30d",
        "project = SCRUM AND status != Done",
        "project = SCRUM OR project = PLAT",
        'NOT status = "Done"',
        "(project = SCRUM AND priority = High) OR labels = customer-reported",
        "project = SCRUM ORDER BY priority DESC",
        "project = SCRUM ORDER BY priority DESC, created ASC",
        'filter = "Bugs assigned to me"',
        'sprint = "Sprint 23 - Notifications"',
        "sprint is EMPTY",
        "sprint = EMPTY",
        "assignee is EMPTY",
        "labels is EMPTY",
        "assignee = NULL",
    ],
)
def test_jql_parses_and_runs(db, jql):
    rows, total = search(db, jql, current_user=_sarah(db), limit=10)
    assert isinstance(total, int)
    assert isinstance(rows, list)
    assert total >= 0


def test_jql_sprint_empty_finds_backlog(db):
    """`sprint is EMPTY` powers the backlog page. Verify it works end-to-end."""
    rows, total = search(db, 'project = SCRUM AND sprint is EMPTY', current_user=_sarah(db), limit=200)
    # Every returned issue must NOT be in any sprint.
    from app.models import SprintIssue
    for r in rows:
        in_sprint = db.query(SprintIssue).filter(SprintIssue.issue_id == r.id).count()
        assert in_sprint == 0, f"{r.id} reported as backlog but is in a sprint"


def test_jql_currentuser_resolves_to_caller(db):
    rows_sarah, total_sarah = search(db, "assignee = currentUser()", current_user=_sarah(db), limit=100)
    rows_priya, total_priya = search(db, "assignee = currentUser()", current_user=_user(db, "user_priya_iyer"), limit=100)
    # Different users get different result counts (because they have different issue lists)
    assert total_sarah != total_priya or total_sarah == 0


def test_jql_substring_text_search(db):
    rows, total = search(db, 'text ~ "regression"', current_user=_sarah(db), limit=50)
    # We seeded an issue with body "fixed in #123" pattern; let's check a known label term in description
    assert total >= 1


def test_jql_text_matches_issue_id(db):
    """`text ~ "PLAT-60"` must surface PLAT-60 itself.

    The global quick-search relies on this so that pasting an issue key into
    the bar resolves to a real hit rather than an empty result (the original
    `text` query searched only summary/description/comments, which silently
    missed exact-key lookups).
    """
    # Pick an issue id that exists and isn't substring-mentioned in any body
    # text - a high filler id is the safest bet.
    target = db.query(Issue).filter_by(id="PLAT-60").one_or_none()
    assert target is not None, "Seed must include PLAT-60 for this regression test"

    rows, total = search(db, 'text ~ "PLAT-60"', current_user=_sarah(db), limit=20)
    assert total >= 1
    assert any(r.id == "PLAT-60" for r in rows), \
        f"PLAT-60 should be a hit when searching by its key; got {[r.id for r in rows]}"


def test_jql_blocked_label_returns_data(db):
    """The seeded "Blocked" saved filter must return real issues.

    Without seeded `blocked`-labeled issues the saved filter shows an empty
    state and the sidebar feels broken. Regression for the demo flow.
    """
    rows, total = search(db, 'labels = "blocked" AND status != "Done"', current_user=_sarah(db), limit=50)
    assert total >= 3, (
        f"Expected the seeded 'Blocked' filter to return >=3 issues, got {total}. "
        f"Re-check seed/content/*_issues.py for 'blocked' label additions."
    )


def test_jql_order_by_priority(db):
    rows, total = search(db, "project = SCRUM ORDER BY priority DESC", current_user=_sarah(db), limit=200)
    # priority text-order isn't numeric, but should be deterministic and stable
    assert len(rows) >= 1


def test_jql_invalid_field_raises(db):
    with pytest.raises(Exception) as ei:
        search(db, "nonexistent = 1", current_user=_sarah(db))
    assert "Unknown JQL field" in str(getattr(ei.value, "detail", ei.value))


def test_jql_unterminated_string_raises(db):
    with pytest.raises(Exception) as ei:
        search(db, 'status = "unterminated', current_user=_sarah(db))
    msg = str(getattr(ei.value, "detail", ei.value))
    assert "JQL parse error" in msg


def test_jql_saved_filter_resolves(db):
    rows, total = search(db, 'filter = "Open support tickets"', current_user=_sarah(db), limit=100)
    # All returned rows should be SUP and not in Resolved/Closed
    for r in rows:
        assert r.project_key == "SUP"
        assert r.status_id not in ("status_sup_resolved", "status_sup_closed")


def test_parse_returns_query_node_with_order(db):
    q = parse_jql('project = SCRUM ORDER BY priority DESC, created ASC')
    assert q.where is not None
    assert [o.field for o in q.order_by] == ["priority", "created"]
    assert [o.desc for o in q.order_by] == [True, False]
