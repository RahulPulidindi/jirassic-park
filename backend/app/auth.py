"""Bearer-token + cookie authentication.

Accepts:
  - `Authorization: Bearer <api_token>` header (REST + MCP)
  - `jp_token` cookie (UI)
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User


def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def get_optional_user(
    db: Annotated[Session, Depends(get_session)],
    authorization: Annotated[Optional[str], Header()] = None,
    jp_token: Annotated[Optional[str], Cookie()] = None,
) -> Optional[User]:
    token = _extract_token(authorization) or jp_token
    if not token:
        return None
    return db.query(User).filter(User.api_token == token).one_or_none()


def get_current_user(
    db: Annotated[Session, Depends(get_session)],
    authorization: Annotated[Optional[str], Header()] = None,
    jp_token: Annotated[Optional[str], Cookie()] = None,
) -> User:
    token = _extract_token(authorization) or jp_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing credentials. Provide `Authorization: Bearer <api_token>` or sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(User).filter(User.api_token == token).one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid api_token.",
        )
    return user


def resolve_user_by_token(db: Session, token: Optional[str]) -> Optional[User]:
    if not token:
        return None
    return db.query(User).filter(User.api_token == token).one_or_none()
