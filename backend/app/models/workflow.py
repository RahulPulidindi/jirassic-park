"""Workflow state machine.

A workflow has many statuses (Backlog, To Do, In Progress, etc.) and many
transitions between them. Projects reference a workflow_id; issues reference
a status_id whose workflow must match.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.clock import now as _now
from app.db import Base


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True)  # e.g. "wf_software_scrum"
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)

    statuses = relationship(
        "WorkflowStatus",
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowStatus.position",
    )
    transitions = relationship(
        "WorkflowTransition", back_populates="workflow", cascade="all, delete-orphan"
    )


class WorkflowStatus(Base):
    """A node in a workflow's state machine."""

    __tablename__ = "workflow_statuses"
    __table_args__ = (UniqueConstraint("workflow_id", "name", name="uq_wf_status_name"),)

    id = Column(String, primary_key=True)  # e.g. "status_scrum_inprogress"
    workflow_id = Column(String, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)  # "In Progress"
    category = Column(String, nullable=False)  # "todo" | "in_progress" | "done"
    color = Column(String, nullable=False, default="#5d6a99")
    board_list = Column(String, nullable=False)  # denormalized swimlane name for boards
    position = Column(Integer, nullable=False, default=0)
    is_initial = Column(Boolean, nullable=False, default=False)

    workflow = relationship("Workflow", back_populates="statuses")


class WorkflowTransition(Base):
    """A directed edge in a workflow's state machine.

    Guards live in `guards_json` and are interpreted by services/workflows.py.
    Known guards: {"requires_role": "lead"}, {"all_subtasks_done": true}.
    """

    __tablename__ = "workflow_transitions"
    __table_args__ = (
        UniqueConstraint("workflow_id", "from_status_id", "to_status_id", name="uq_wf_transition"),
    )

    id = Column(String, primary_key=True)
    workflow_id = Column(String, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    from_status_id = Column(String, ForeignKey("workflow_statuses.id"), nullable=False)
    to_status_id = Column(String, ForeignKey("workflow_statuses.id"), nullable=False)
    name = Column(String, nullable=False)  # human label e.g. "Start work"
    guards_json = Column(Text, nullable=True)

    workflow = relationship("Workflow", back_populates="transitions")
    from_status = relationship("WorkflowStatus", foreign_keys=[from_status_id])
    to_status = relationship("WorkflowStatus", foreign_keys=[to_status_id])
