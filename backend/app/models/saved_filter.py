"""Saved JQL filters - named queries users star in the sidebar."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.clock import now as _now
from app.db import Base


class SavedFilter(Base):
    __tablename__ = "saved_filters"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    jql = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    shared = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=_now)

    owner = relationship("User")
