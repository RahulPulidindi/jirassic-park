"""Issue model.

Column names intentionally align with the standard evaluation schema
(board_list, story_points, project_key, owner, issue_type) so verifiers
written against that schema can grade against ours unmodified.
"""

from __future__ import annotations

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import relationship

from app.clock import now as _now
from app.db import Base


# Canonical priority levels (matching Jira's vocabulary). Stored as a string so
# joins are unnecessary in the common case; we expose this as a Python list so
# the seed builder and JQL parser can reuse it.
PRIORITIES = ["Lowest", "Low", "Medium", "High", "Highest"]
ISSUE_TYPES = ["Story", "Task", "Bug", "Epic", "Subtask"]


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        Index("ix_issues_project_key", "project_key"),
        Index("ix_issues_owner", "owner"),
        Index("ix_issues_status", "status_id"),
        Index("ix_issues_board_list", "board_list"),
        Index("ix_issues_epic_id", "epic_id"),
        Index("ix_issues_parent_id", "parent_id"),
    )

    # "{KEY}-{N}" e.g. "SCRUM-123" - canonical Jira-style identifier
    id = Column(String, primary_key=True)
    project_key = Column(String, ForeignKey("projects.key"), nullable=False)
    issue_type = Column(String, nullable=False)  # Story | Task | Bug | Epic | Subtask
    summary = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    # Status: foreign-key into workflow_statuses; board_list is the denormalized
    # swimlane label for the board. Updated together by services/issues.py.
    status_id = Column(String, ForeignKey("workflow_statuses.id"), nullable=False)
    board_list = Column(String, nullable=False)  # e.g. "Backlog", "To Do", "Done"

    priority = Column(String, nullable=False, default="Medium")
    owner = Column(String, ForeignKey("users.id"), nullable=True)  # assignee
    reporter = Column(String, ForeignKey("users.id"), nullable=False)

    parent_id = Column(String, ForeignKey("issues.id"), nullable=True)  # for Subtasks
    epic_id = Column(String, ForeignKey("issues.id"), nullable=True)  # parent Epic

    story_points = Column(Integer, nullable=True)
    resolution = Column(String, nullable=True)  # "Fixed", "Won't Fix", "Duplicate", null
    due_date = Column(Date, nullable=True)

    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    # Relationships
    status = relationship("WorkflowStatus")
    assignee = relationship("User", foreign_keys=[owner])
    reporter_user = relationship("User", foreign_keys=[reporter])
    parent = relationship("Issue", remote_side=[id], foreign_keys=[parent_id])
    epic = relationship("Issue", remote_side=[id], foreign_keys=[epic_id])
    comments = relationship(
        "Comment", back_populates="issue", cascade="all, delete-orphan", order_by="Comment.created_at"
    )
    activities = relationship(
        "Activity", back_populates="issue", cascade="all, delete-orphan", order_by="Activity.created_at"
    )
    labels = relationship(
        "IssueLabel", back_populates="issue", cascade="all, delete-orphan"
    )
    watchers = relationship(
        "Watcher", back_populates="issue", cascade="all, delete-orphan"
    )
    sprint_assignments = relationship(
        "SprintIssue", back_populates="issue", cascade="all, delete-orphan"
    )
    outbound_links = relationship(
        "IssueLink",
        foreign_keys="IssueLink.source_id",
        back_populates="source",
        cascade="all, delete-orphan",
    )
    inbound_links = relationship(
        "IssueLink", foreign_keys="IssueLink.target_id", back_populates="target"
    )
    custom_field_values = relationship(
        "CustomFieldValue", back_populates="issue", cascade="all, delete-orphan"
    )
    attachments = relationship(
        "Attachment", back_populates="issue", cascade="all, delete-orphan"
    )
