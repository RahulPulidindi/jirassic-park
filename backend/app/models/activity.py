"""Audit log. Every state mutation through the services layer writes here.

The verifier-friendly invariant is: `activities` is the side-channel for the
"history" UI tab, and is what `IgnoreConfig` excludes when computing diff
invariants in scenario verifiers.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from app.clock import now as _now
from app.db import Base


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (
        Index("ix_activities_issue_id", "issue_id"),
        Index("ix_activities_actor_id", "actor_id"),
        Index("ix_activities_created_at", "created_at"),
    )

    id = Column(String, primary_key=True)
    actor_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Most activities are scoped to an issue; entity_type/entity_id lets us also
    # log project-level activity (sprint started, board updated, etc.).
    issue_id = Column(String, ForeignKey("issues.id", ondelete="CASCADE"), nullable=True)
    entity_type = Column(String, nullable=False, default="issue")  # issue | sprint | project | board
    entity_id = Column(String, nullable=False)

    # action vocabulary: created | updated | transitioned | commented | assigned
    #                    | linked | unlinked | labeled | unlabeled | watched
    #                    | unwatched | sprint_added | sprint_removed
    #                    | sprint_started | sprint_completed | reset
    action = Column(String, nullable=False)
    field = Column(String, nullable=True)  # which field changed, when action=updated
    from_value = Column(Text, nullable=True)
    to_value = Column(Text, nullable=True)
    comment_body = Column(Text, nullable=True)  # for action=commented, mirrors comment body

    created_at = Column(DateTime, nullable=False, default=_now)

    issue = relationship("Issue", back_populates="activities")
    actor = relationship("User")
