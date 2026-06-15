"""Universal clock for the environment.

Every timestamp written by the services layer (issue created_at, activity
created_at, comment created_at, sprint start_date, ...) flows through `now()`
here. This is what makes the environment reproducible:

- Tests can freeze the clock so two runs of the same scenario produce identical
  `activities` rows, identical `state.db` hashes, and identical JQL results.
- Eval rollouts can pin the env to a specific instant so JQL like
  "updated > -7d" returns a stable set across runs (otherwise the same seed
  "ages" silently as the wall clock advances).
- The seed builder bakes timestamps relative to `now()`, so a fresh `seed.db`
  produced six months from today still shows "Sprint 23 in progress, started 5
  days ago" -- not "started 6 months ago".

Configured at process start via the JP_CLOCK env var:

    unset / "real"           wall clock (default; what humans expect)
    "frozen:<iso8601>"       always return this instant
    "tick:<iso8601>"         start at this instant; every call to now() advances
                              by 1 us. Use this in tests / parity rollouts: same
                              call sequence -> same timestamps, every row gets a
                              unique created_at so order-by stays stable.
    "offset:<seconds>"       wall clock + offset (positive = future)

At runtime, administrators can also set the clock through
`POST /api/admin/clock` (handled in `app.api.admin`). Test code uses the
`freeze`, `advance`, `unfreeze` helpers below.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass
class _State:
    mode: str = "real"           # "real" | "frozen" | "tick" | "offset"
    frozen: Optional[datetime] = None
    offset: timedelta = timedelta()
    # Tick state: counts microseconds advanced from `frozen`.
    tick_us: int = 0


_state = _State()


# Per-call tick advancement in microseconds. 1us is enough granularity to
# preserve ordering even in tight loops; SQLite DateTime stores us precision.
_TICK_STEP_US = 1


def _parse_iso(s: str) -> datetime:
    """Parse an ISO-8601 string into a UTC-naive datetime.

    The rest of the project stores timestamps as UTC-naive (the SQLAlchemy
    `DateTime` columns), so we normalize aware datetimes back to naive after
    converting to UTC.
    """
    s = s.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def configure_from_env() -> None:
    """Read JP_CLOCK and update internal state.

    Called once at import time and again any time the admin clock endpoint
    rewrites the env var (so a single process can be retargeted live).
    """
    raw = os.environ.get("JP_CLOCK", "real").strip()
    if not raw or raw == "real":
        _state.mode = "real"
        _state.frozen = None
        _state.offset = timedelta()
        return
    if raw.startswith("frozen:"):
        _state.mode = "frozen"
        _state.frozen = _parse_iso(raw[len("frozen:"):])
        _state.offset = timedelta()
        _state.tick_us = 0
        return
    if raw.startswith("tick:"):
        _state.mode = "tick"
        _state.frozen = _parse_iso(raw[len("tick:"):])
        _state.offset = timedelta()
        _state.tick_us = 0
        return
    if raw.startswith("offset:"):
        _state.mode = "offset"
        _state.frozen = None
        _state.offset = timedelta(seconds=float(raw[len("offset:"):]))
        _state.tick_us = 0
        return
    raise ValueError(
        f"JP_CLOCK={raw!r} not understood. "
        "Use 'real', 'frozen:<iso8601>', 'tick:<iso8601>', or 'offset:<seconds>'."
    )


def now() -> datetime:
    """The env's current time, in UTC-naive form. Cheap to call."""
    if _state.mode == "frozen" and _state.frozen is not None:
        return _state.frozen
    if _state.mode == "tick" and _state.frozen is not None:
        result = _state.frozen + timedelta(microseconds=_state.tick_us)
        _state.tick_us += _TICK_STEP_US
        return result
    if _state.mode == "offset":
        return datetime.utcnow() + _state.offset
    return datetime.utcnow()


def describe() -> dict:
    """Snapshot of the current clock state, for /api/clock and debugging.

    Note: in `tick` mode `now()` advances on every call, so we peek at the
    current anchor + counter instead of calling `now()` (which would consume a
    tick just to render this dict).
    """
    if _state.mode == "tick" and _state.frozen is not None:
        peek = (_state.frozen + timedelta(microseconds=_state.tick_us)).isoformat() + "Z"
    else:
        peek = now().isoformat() + "Z"
    return {
        "mode": _state.mode,
        "now": peek,
        "wall_now": datetime.utcnow().isoformat() + "Z",
        "frozen_at": _state.frozen.isoformat() + "Z" if _state.frozen else None,
        "offset_seconds": _state.offset.total_seconds() if _state.mode == "offset" else 0.0,
        "tick_us": _state.tick_us if _state.mode == "tick" else None,
    }


# ---- runtime control ------------------------------------------------------


def freeze(at: datetime | str) -> None:
    """Pin the clock to a given instant. Idempotent."""
    _state.mode = "frozen"
    _state.frozen = at if isinstance(at, datetime) else _parse_iso(at)
    _state.offset = timedelta()
    _state.tick_us = 0


def tick_from(at: datetime | str) -> None:
    """Switch to tick mode, anchored at `at`, resetting the counter."""
    _state.mode = "tick"
    _state.frozen = at if isinstance(at, datetime) else _parse_iso(at)
    _state.offset = timedelta()
    _state.tick_us = 0


def reset_ticks() -> None:
    """Reset the tick counter (for between-test isolation)."""
    _state.tick_us = 0


def set_offset(seconds: float) -> None:
    """Run on wall-clock + a fixed offset. Useful for 'jump 2h into the future'."""
    _state.mode = "offset"
    _state.frozen = None
    _state.offset = timedelta(seconds=seconds)


def unfreeze() -> None:
    """Restore real wall-clock mode."""
    _state.mode = "real"
    _state.frozen = None
    _state.offset = timedelta()
    _state.tick_us = 0


def advance(seconds: float) -> None:
    """Shift the clock forward by `seconds`.

    - In frozen mode: moves the frozen instant forward.
    - In offset mode: increases the offset.
    - In real mode: switches to offset mode with this delta.
    """
    if _state.mode == "frozen" and _state.frozen is not None:
        _state.frozen = _state.frozen + timedelta(seconds=seconds)
    elif _state.mode == "offset":
        _state.offset = _state.offset + timedelta(seconds=seconds)
    else:
        _state.mode = "offset"
        _state.offset = timedelta(seconds=seconds)


configure_from_env()
