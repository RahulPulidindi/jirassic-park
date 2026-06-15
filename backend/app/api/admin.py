"""Admin routes - reset, reseed, clock control."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import clock
from app.auth import get_current_user
from app.db import get_session
from app.models import User
from app.schemas.api import AdminResetOut
from app.services import permissions

router = APIRouter()


@router.post("/reset", response_model=AdminResetOut)
def reset(
    user: Annotated[User, Depends(get_current_user)],
    _db: Annotated[Session, Depends(get_session)],
):
    """Restore state.db from the immutable seed.db. Admin-only."""
    permissions.require(_db, user, "admin.reset")
    # CRITICAL: release this request's checked-out connection BEFORE the
    # reset disposes the engine, otherwise the pool ends up with a dangling
    # invalidated connection and the next request hits "disk I/O error".
    _db.close()
    from app.db import reset_state_from_seed
    reset_state_from_seed()
    return AdminResetOut(success=True, message="state.db restored from seed.db.")


@router.post("/reseed", response_model=AdminResetOut)
def reseed(
    user: Annotated[User, Depends(get_current_user)],
    _db: Annotated[Session, Depends(get_session)],
):
    """Rebuild seed.db from fixtures, then copy to state.db. Admin-only."""
    permissions.require(_db, user, "admin.reseed")
    _db.close()  # see admin.reset for why
    from app.seed.builder import rebuild
    rebuild()
    return AdminResetOut(success=True, message="seed.db rebuilt from fixtures and applied.")


class ClockSetIn(BaseModel):
    mode: str  # "real" | "frozen" | "offset" | "advance"
    at: Optional[str] = None         # ISO timestamp for "frozen"
    seconds: Optional[float] = None  # delta for "offset" / "advance"


@router.post("/clock", response_model=dict)
def set_clock(
    payload: ClockSetIn,
    user: Annotated[User, Depends(get_current_user)],
    _db: Annotated[Session, Depends(get_session)],
):
    """Reconfigure the env's universal clock at runtime. Admin-only.

    Examples:
      {"mode":"frozen","at":"2026-05-27T12:00:00Z"}   pin to a fixed instant
      {"mode":"offset","seconds":3600}                wall-clock + 1h
      {"mode":"advance","seconds":86400}              jump 1 day forward
      {"mode":"real"}                                 restore wall clock
    """
    permissions.require(_db, user, "admin.reset")  # same gate as reset/reseed
    m = payload.mode.lower()
    if m == "real":
        clock.unfreeze()
    elif m == "frozen":
        if not payload.at:
            raise HTTPException(422, "mode='frozen' requires 'at' (ISO timestamp).")
        clock.freeze(payload.at)
    elif m == "offset":
        if payload.seconds is None:
            raise HTTPException(422, "mode='offset' requires 'seconds'.")
        clock.set_offset(payload.seconds)
    elif m == "advance":
        if payload.seconds is None:
            raise HTTPException(422, "mode='advance' requires 'seconds'.")
        clock.advance(payload.seconds)
    else:
        raise HTTPException(422, f"Unknown clock mode '{payload.mode}'. "
                                  "Use one of: real, frozen, offset, advance.")
    return clock.describe()
