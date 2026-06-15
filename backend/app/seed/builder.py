"""Seed builder.

Owns the lifecycle of the SQLite databases on disk:
  - `seed.db`    immutable baseline produced from fixtures + content modules.
  - `state.db`   mutable working copy used by the running app.

CLI:
    python -m app.seed.builder --ensure     # create state.db if missing
    python -m app.seed.builder --reset      # cp seed.db -> state.db
    python -m app.seed.builder --rebuild    # rebuild seed.db from fixtures

`ensure` is also called from the container entrypoint. It enforces a schema
version: if the on-disk DBs were produced by an older version of the code
(missing columns, missing tables), `ensure` rebuilds from fixtures instead of
limping along with a stale schema. This is the project's lightweight
alternative to Alembic migrations - acceptable because state is meant to be
reproducible from the seed, not preserved across upgrades.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path

from app.config import settings
from app.db import (
    Base,
    dispose_engine,
    get_engine,
    init_engine,
    reset_state_from_seed,
    snapshot_state_to_seed,
)

logger = logging.getLogger(__name__)


# Bump this any time the SQL schema or seed contents change in a way that
# existing seed.db / state.db files won't satisfy. `ensure()` reads
# `PRAGMA user_version` and forces a rebuild when it doesn't match.
SCHEMA_VERSION = 2


def _read_schema_version(db_path: Path) -> int:
    if not db_path.exists():
        return -1
    try:
        with sqlite3.connect(str(db_path)) as conn:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.DatabaseError:
        return -1


def _write_schema_version(db_path: Path, version: int) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(f"PRAGMA user_version = {int(version)}")
        conn.commit()


def ensure() -> None:
    """Create or upgrade state.db so the running app sees the current schema."""
    s = settings()
    Path(s.data_dir).mkdir(parents=True, exist_ok=True)

    state_v = _read_schema_version(s.state_db_path)
    seed_v = _read_schema_version(s.seed_db_path)

    # Fresh volume.
    if state_v < 0 and seed_v < 0:
        logger.info("First boot - building schema and seed snapshot")
        rebuild()
        return

    # state.db missing but seed.db present and current - restore from seed.
    if state_v < 0 and seed_v == SCHEMA_VERSION:
        logger.info("state.db missing but seed.db present; restoring from seed")
        reset_state_from_seed()
        return

    # Either DB is stale - regenerate the whole baseline. Users who care
    # about preserving in-flight state should snapshot before upgrading.
    if state_v != SCHEMA_VERSION or seed_v != SCHEMA_VERSION:
        logger.info(
            "Schema version drift (state=%s, seed=%s, want=%s); rebuilding seed",
            state_v, seed_v, SCHEMA_VERSION,
        )
        rebuild()
        return

    init_engine()
    import_all_models()
    Base.metadata.create_all(bind=get_engine())


def rebuild() -> None:
    """Wipe state.db, recreate schema, run fixtures, snapshot to seed.db."""
    s = settings()
    dispose_engine()
    if s.state_db_path.exists():
        s.state_db_path.unlink()
    init_engine()
    import_all_models()
    Base.metadata.create_all(bind=get_engine())
    _populate_fixtures()
    _write_schema_version(s.state_db_path, SCHEMA_VERSION)
    snapshot_state_to_seed()
    _write_schema_version(s.seed_db_path, SCHEMA_VERSION)
    logger.info(
        "Seed snapshot written to %s (schema v%d)", s.seed_db_path, SCHEMA_VERSION
    )


def reset() -> None:
    """Restore state.db from seed.db."""
    s = settings()
    if not s.seed_db_path.exists():
        logger.info("No seed.db yet - building one first")
        rebuild()
        return
    reset_state_from_seed()
    logger.info("state.db reset from %s", s.seed_db_path)


def import_all_models() -> None:
    """Import all model modules so Base.metadata sees every table."""
    try:
        from app.models import (  # noqa: F401
            activity,
            attachment,
            board,
            comment,
            custom_field,
            issue,
            label,
            link,
            project,
            saved_filter,
            sprint,
            user,
            watcher,
            workflow,
        )
    except ImportError:
        logger.warning("Some model modules not yet present; schema will be partial")


def _populate_fixtures() -> None:
    """Populate the DB from fixtures. Real implementation arrives in the seed phase."""
    try:
        from app.seed.populate import populate

        populate()
    except ImportError:
        logger.info("No populate module yet; seed will be empty (skeleton mode)")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Jirassic Park seed builder")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ensure", action="store_true", help="Create state.db if missing")
    group.add_argument("--reset", action="store_true", help="Restore state.db from seed.db")
    group.add_argument("--rebuild", action="store_true", help="Rebuild seed.db from fixtures")
    args = parser.parse_args()

    if args.ensure:
        ensure()
    elif args.reset:
        reset()
    elif args.rebuild:
        rebuild()


if __name__ == "__main__":
    main()
