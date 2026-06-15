"""Watchers and votes on issues."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from app.clock import now as _now
from app.db import Base


class Watcher(Base):
    __tablename__ = "watchers"

    issue_id = Column(String, ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime, nullable=False, default=_now)

    issue = relationship("Issue", back_populates="watchers")
    user = relationship("User")


class Vote(Base):
    __tablename__ = "votes"

    issue_id = Column(String, ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime, nullable=False, default=_now)
