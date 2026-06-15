"""Sprint and sprint_issues junction."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from app.clock import now as _now
from app.db import Base


class Sprint(Base):
    __tablename__ = "sprints"

    id = Column(String, primary_key=True)  # e.g. "sprint_scrum_23"
    project_key = Column(String, ForeignKey("projects.key"), nullable=False)
    name = Column(String, nullable=False)
    state = Column(String, nullable=False, default="future")  # future | active | closed
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    goal = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)

    project = relationship("Project", back_populates="sprints")
    issues = relationship(
        "SprintIssue", back_populates="sprint", cascade="all, delete-orphan"
    )


class SprintIssue(Base):
    """Junction between sprints and issues. `rank` is a string for stable lexicographic ordering."""

    __tablename__ = "sprint_issues"
    __table_args__ = (Index("ix_sprint_issues_issue_id", "issue_id"),)

    sprint_id = Column(String, ForeignKey("sprints.id", ondelete="CASCADE"), primary_key=True)
    issue_id = Column(String, ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True)
    rank = Column(String, nullable=False, default="0|hzzzzz:")
    added_at = Column(DateTime, nullable=False, default=_now)

    sprint = relationship("Sprint", back_populates="issues")
    issue = relationship("Issue", back_populates="sprint_assignments")
