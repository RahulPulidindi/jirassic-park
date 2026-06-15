"""Labels: flat tags applied to issues."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import relationship

from app.db import Base


class Label(Base):
    __tablename__ = "labels"

    name = Column(String, primary_key=True)  # natural key


class IssueLabel(Base):
    """Junction between issues and labels."""

    __tablename__ = "issue_labels"

    issue_id = Column(String, ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True)
    label_name = Column(String, ForeignKey("labels.name", ondelete="CASCADE"), primary_key=True)

    issue = relationship("Issue", back_populates="labels")
    label = relationship("Label")
