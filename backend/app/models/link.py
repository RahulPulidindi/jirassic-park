"""Issue links: directional relationships between issues.

Link types use Jira's vocabulary: blocks/blocked by, relates, duplicates, clones,
caused by. Stored as a single `link_type` plus a `direction` we can compose.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.clock import now as _now
from app.db import Base


LINK_TYPES = ["blocks", "relates", "duplicates", "clones", "causes"]


class IssueLink(Base):
    __tablename__ = "issue_links"
    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "link_type", name="uq_issue_link"),
    )

    id = Column(String, primary_key=True)
    source_id = Column(String, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    target_id = Column(String, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    link_type = Column(String, nullable=False)  # blocks | relates | duplicates | clones | causes
    created_at = Column(DateTime, nullable=False, default=_now)

    source = relationship("Issue", foreign_keys=[source_id], back_populates="outbound_links")
    target = relationship("Issue", foreign_keys=[target_id], back_populates="inbound_links")
