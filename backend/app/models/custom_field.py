"""Custom fields. Values are JSON-encoded blobs scoped to (issue, field)."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.db import Base


class CustomField(Base):
    __tablename__ = "custom_fields"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    field_type = Column(String, nullable=False)  # text | number | select | date | multi_select
    project_keys = Column(Text, nullable=False, default="[]")  # JSON array; empty = all
    options = Column(Text, nullable=True)  # JSON array of option strings for select types


class CustomFieldValue(Base):
    __tablename__ = "custom_field_values"

    issue_id = Column(String, ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True)
    custom_field_id = Column(
        String, ForeignKey("custom_fields.id", ondelete="CASCADE"), primary_key=True
    )
    value = Column(Text, nullable=True)  # JSON-encoded scalar/array

    issue = relationship("Issue", back_populates="custom_field_values")
    custom_field = relationship("CustomField")
