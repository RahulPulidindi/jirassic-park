"""Tests for the universal clock.

The clock is the linchpin for reproducible eval. These tests guard the contract:
- `now()` honours frozen/offset modes.
- Writing through services + models picks up the frozen instant.
- Test isolation: changes from one test don't leak (conftest re-applies the
  session-wide freeze on every test via _reset_state -> nothing, but we also
  restore after explicit per-test overrides).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app import clock
from app.services import issues as issue_svc


@pytest.fixture(autouse=True)
def _restore_session_clock():
    """Any test that diddles the clock must put it back so siblings stay stable."""
    yield
    clock.freeze("2026-05-27T12:00:00Z")


def test_now_returns_frozen_instant():
    clock.freeze("2030-01-01T00:00:00Z")
    n = clock.now()
    assert n == datetime(2030, 1, 1, 0, 0, 0)


def test_advance_moves_frozen_clock_forward():
    clock.freeze("2030-01-01T00:00:00Z")
    clock.advance(3600)
    assert clock.now() == datetime(2030, 1, 1, 1, 0, 0)


def test_offset_mode_tracks_wall_clock_plus_delta():
    # offset mode reads `datetime.utcnow()` and adds the delta; we can't pin
    # the wall clock here, so just assert "the gap is roughly right".
    clock.set_offset(86_400)  # +1 day
    n = clock.now()
    wall = datetime.utcnow()
    gap = (n - wall).total_seconds()
    assert 86_390 < gap < 86_410  # 10s tolerance to dodge CI jitter


def test_describe_shape():
    clock.freeze("2026-05-27T12:00:00Z")
    snap = clock.describe()
    assert snap["mode"] == "frozen"
    assert snap["now"].startswith("2026-05-27T12:00:00")
    assert snap["frozen_at"].startswith("2026-05-27T12:00:00")


def test_invalid_mode_raises():
    with pytest.raises(ValueError):
        import os
        os.environ["JP_CLOCK"] = "moonshine"
        try:
            clock.configure_from_env()
        finally:
            os.environ["JP_CLOCK"] = "frozen:2026-05-27T12:00:00Z"
            clock.configure_from_env()


def test_issue_create_uses_frozen_clock(db):
    """Smoke test: every write path goes through clock.now()."""
    clock.freeze("2026-05-27T12:00:00Z")
    admin = db.query(__import__("app.models", fromlist=["User"]).User).filter_by(id="user_admin").one()
    issue = issue_svc.create_issue(
        db, admin,
        issue_svc.CreateIssueInput(project_key="SCRUM", issue_type="Task", summary="Clock check"),
    )
    assert issue.created_at == datetime(2026, 5, 27, 12, 0, 0)
    assert issue.updated_at == datetime(2026, 5, 27, 12, 0, 0)

    # After advancing, an update writes the new instant to updated_at.
    clock.advance(60)
    issue_svc.update_issue(db, admin, issue.id, {"priority": "High"})
    assert issue.created_at == datetime(2026, 5, 27, 12, 0, 0)
    assert issue.updated_at == datetime(2026, 5, 27, 12, 1, 0)
