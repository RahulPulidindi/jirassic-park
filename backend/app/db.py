"""SQLAlchemy engine and session management.

Single SQLite database (`state.db`) per container. An immutable `seed.db` lives
next to it on the same volume so `POST /api/admin/reset` can restore by copying.
"""

from __future__ import annotations

import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base

from app.config import settings


Base = declarative_base()

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _make_engine(url: str) -> Engine:
    engine = create_engine(
        url,
        future=True,
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    return engine


def init_engine() -> Engine:
    """Initialize the global engine. Called at app startup and after reset."""
    global _engine, _SessionLocal
    s = settings()
    Path(s.data_dir).mkdir(parents=True, exist_ok=True)
    _engine = _make_engine(s.state_db_url)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        return init_engine()
    return _engine


def dispose_engine() -> None:
    """Tear down the engine so the SQLite file can be replaced."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for a transactional session."""
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a Session."""
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def reset_state_from_seed() -> None:
    """Restore state.db from the immutable seed.db backup.

    SQLite runs in WAL mode. Naively doing ``shutil.copy(seed -> state)``
    breaks in two ways:

      1. The previous session's ``state.db-wal`` / ``state.db-shm`` sidecars
         are left on disk. The next open replays them on top of the freshly-
         copied file (this is SQLite's crash-recovery semantics — exactly
         what we don't want here) and the "reset" silently restores nothing.
      2. Even if you delete the sidecars, toggling ``PRAGMA journal_mode``
         on the same file from within the running process and then opening
         a new WAL connection leaves the per-process SQLite library in an
         inconsistent state and the next query fails with ``disk I/O error``.

    The robust approach is to use SQLite's online backup API — the same one
    ``snapshot_state_to_seed`` uses in the opposite direction. It writes the
    seed's pages into state.db through a real SQLite connection, so WAL,
    shared-memory, and the destination's pragmas stay coherent. We then
    truncate-checkpoint state.db so the next opener sees zero WAL pages.
    """
    s = settings()
    if not s.seed_db_path.exists():
        raise FileNotFoundError(
            f"seed.db not found at {s.seed_db_path}. Run the seed builder first."
        )
    dispose_engine()

    # Remove any leftover sidecars *before* opening fresh connections so
    # SQLite can't pick them up. Also remove state.db itself so the new
    # connection creates a brand-new file rather than racing with whatever
    # the engine pool might still hold a reference to.
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = s.state_db_path.with_name(s.state_db_path.name + suffix)
        if p.exists():
            p.unlink()

    # Online backup: faithful copy through a real SQLite connection.
    src = sqlite3.connect(str(s.seed_db_path))
    dst = sqlite3.connect(str(s.state_db_path))
    try:
        with dst:
            src.backup(dst)
        # Drain any WAL produced by the backup itself so the next opener
        # sees a clean main file with empty sidecars.
        dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        src.close()
        dst.close()

    init_engine()


def snapshot_state_to_seed() -> None:
    """Snapshot the current state.db into seed.db (used by the seed builder)."""
    s = settings()
    if not s.state_db_path.exists():
        raise FileNotFoundError(f"state.db not found at {s.state_db_path}.")

    # Use SQLite backup API for safety even with WAL connections open.
    src = sqlite3.connect(str(s.state_db_path))
    dst = sqlite3.connect(str(s.seed_db_path))
    try:
        with dst:
            src.backup(dst)
    finally:
        src.close()
        dst.close()
