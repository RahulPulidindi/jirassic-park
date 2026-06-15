"""Auth: login (exchange token for session cookie), logout, me."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_session
from app.models import User
from app.schemas.api import LoginIn, UserMeOut, UserOut

router = APIRouter()


@router.post("/login", response_model=UserMeOut)
def login(payload: LoginIn, db: Annotated[Session, Depends(get_session)], response: Response):
    """Exchange an api_token for a session.

    For the browser UI, the same token is set as an httpOnly cookie so the SPA
    can call /api/* without re-passing the bearer.
    """
    user = db.query(User).filter(User.api_token == payload.api_token).one_or_none()
    if user is None:
        raise HTTPException(401, "Invalid api_token.")
    # Set cookie for UI (the cookie value is the same api_token).
    response.set_cookie(
        "jp_token", payload.api_token,
        httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30,
    )
    return UserMeOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie("jp_token")
    return Response(status_code=204)


@router.get("/me", response_model=UserMeOut)
def me(user: Annotated[User, Depends(get_current_user)]):
    return UserMeOut.model_validate(user)
