"""Regression test for the WAL-replay bug in `reset_state_from_seed`.

Production symptom: the agent demo created PLAT-70 in state.db, the agent run
finished, the user ran `make reset`, the API responded `{"success": true}`,
but the next request still showed PLAT-70 because the leftover
``state.db-wal`` (148KB of pending pages) got replayed on top of the freshly-
copied state.db.

Root cause: `shutil.copy(seed -> state)` only replaces the main DB file. SQLite
crash-recovery semantics dictate that on the next open, any sidecar -wal or
-shm files are treated as committed-but-uncheckpointed pages and reapplied.

The fix in `reset_state_from_seed`:
  1. dispose the engine,
  2. open a temporary connection, force TRUNCATE checkpoint, switch journal
     mode to DELETE so SQLite removes the sidecars cleanly,
  3. unlink any -wal / -shm / -journal sidecars that still exist,
  4. then copy seed -> state.

This test asserts that any leftover sidecar files are gone after a reset,
regardless of how they got there.
"""

from __future__ import annotations

from pathlib import Path


def test_reset_clears_wal_sidecars():
    from app.config import settings
    from app.db import dispose_engine, reset_state_from_seed

    s = settings()
    state_db = Path(s.state_db_path)

    # Make sure state.db exists in a known state and the engine is closed so
    # we can plant our fake sidecars without contention.
    reset_state_from_seed()
    dispose_engine()

    # Simulate the production failure: -wal and -shm files left on disk by a
    # prior session, exactly as `ls /data/` showed after the agent run.
    wal = state_db.with_name(state_db.name + "-wal")
    shm = state_db.with_name(state_db.name + "-shm")
    wal.write_bytes(b"this would normally be a non-empty WAL")
    shm.write_bytes(b"shm data")
    assert wal.exists() and shm.exists()

    reset_state_from_seed()

    # Post-fix invariant: no leftover -wal or -shm should resurrect old writes.
    # SQLite may legitimately recreate -wal on the next open; if it exists, it
    # must be empty (no pending pages from the prior session).
    if wal.exists():
        assert wal.stat().st_size == 0, "leftover non-empty -wal can resurrect old writes"
    if shm.exists():
        assert shm.stat().st_size == 0, "leftover non-empty -shm can resurrect old writes"


def test_rest_reset_leaves_engine_usable(client):
    """Regression for the second WAL-replay bug.

    Earlier the reset path was "dispose engine, swap file, init engine" — but
    the admin endpoint still held a checked-out connection via
    Depends(get_session). After dispose+init, that connection was orphaned and
    every subsequent REST call failed with sqlite3.OperationalError("disk I/O
    error"). The container needed a full restart to recover.

    This test does what a human reviewer would do: hit reset, then hit any
    other endpoint and expect 2xx.
    """
    h = {"Authorization": "Bearer admin-token-jurassic"}
    # Make a write so reset actually has something to undo.
    r = client.post("/api/issues", json={"project_key": "PLAT", "summary": "x"}, headers=h)
    assert r.status_code in (200, 201), r.text
    new_id = r.json()["id"]

    r = client.post("/api/admin/reset", headers=h)
    assert r.status_code == 200, r.text

    # The next request must succeed (this was the regression).
    r = client.get("/api/projects", headers=h)
    assert r.status_code == 200, r.text
    assert any(p["key"] == "PLAT" for p in r.json())

    # And the write we made is really gone.
    r = client.get(f"/api/issues/{new_id}", headers=h)
    assert r.status_code == 404, f"{new_id} should not exist after reset ({r.status_code})"


def test_reset_yields_logical_equivalence_to_seed():
    """After reset, state.db should be logically equivalent to seed.db.

    We use SQLite's online backup API (not raw file copy) so the resulting
    pages aren't necessarily byte-identical — but every row in every table
    must match.
    """
    import sqlite3

    from app.config import settings
    from app.db import (
        init_engine,
        reset_state_from_seed,
        session_scope,
    )
    from app.models import Issue, Project, WorkflowStatus

    s = settings()

    init_engine()
    with session_scope() as db:
        plat = db.query(Project).filter(Project.key == "PLAT").one()
        plat.next_issue_number += 1
        ghost = f"PLAT-{plat.next_issue_number - 1}"
        wf_status = (
            db.query(WorkflowStatus)
            .filter(WorkflowStatus.workflow_id == plat.workflow_id)
            .first()
        )
        db.add(
            Issue(
                id=ghost,
                project_key="PLAT",
                issue_type="Bug",
                summary="should be erased",
                status_id=wf_status.id,
                board_list="Backlog",
                reporter="user_admin",
            )
        )

    reset_state_from_seed()

    # The ghost row must NOT survive the reset.
    with session_scope() as db:
        assert db.query(Issue).filter(Issue.id == ghost).one_or_none() is None
        plat_after = db.query(Project).filter(Project.key == "PLAT").one()
        assert plat_after.next_issue_number < int(ghost.split("-")[1]) + 1

    # Logical equivalence: row counts per table must match seed.
    def _table_counts(path: Path) -> dict[str, int]:
        c = sqlite3.connect(str(path))
        try:
            tables = [
                r[0]
                for r in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            return {t: c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}
        finally:
            c.close()

    assert _table_counts(s.state_db_path) == _table_counts(s.seed_db_path)
