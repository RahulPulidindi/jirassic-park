"""Project model."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.clock import now as _now
from app.db import Base


class Project(Base):
    __tablename__ = "projects"

    key = Column(String, primary_key=True)  # e.g. "SCRUM" (natural FK from issues)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    project_type = Column(String, nullable=False, default="software")  # software | service
    lead_id = Column(String, ForeignKey("users.id"), nullable=True)
    default_assignee = Column(String, ForeignKey("users.id"), nullable=True)
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False)
    avatar_color = Column(String, nullable=False, default="#3d63d9")
    next_issue_number = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    lead = relationship("User", foreign_keys=[lead_id])
    workflow = relationship("Workflow")
    boards = relationship("Board", back_populates="project", cascade="all, delete-orphan")
    sprints = relationship("Sprint", back_populates="project", cascade="all, delete-orphan")
