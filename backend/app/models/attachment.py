"""Attachment model. Files referenced by issues; blob_path is a relative path."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.clock import now as _now
from app.db import Base


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(String, primary_key=True)
    issue_id = Column(String, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String, nullable=False)
    mime_type = Column(String, nullable=False, default="application/octet-stream")
    size = Column(Integer, nullable=False, default=0)
    blob_path = Column(String, nullable=False)
    uploader_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now)

    issue = relationship("Issue", back_populates="attachments")
    uploader = relationship("User")
