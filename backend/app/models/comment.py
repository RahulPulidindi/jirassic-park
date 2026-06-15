"""Comment model. Markdown body, threaded via `parent_comment_id`.

`mentions` is a denormalized list of user ids that the comment refers to via
`@user_*` syntax. It's computed by `services.issues.add_comment` (the only
write path) so the JQL parser and notifications feed don't have to re-parse the
body on every read.
"""

from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from app.clock import now as _now
from app.db import Base


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (Index("ix_comments_issue_id", "issue_id"),)

    id = Column(String, primary_key=True)
    issue_id = Column(String, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(String, ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    parent_comment_id = Column(String, ForeignKey("comments.id"), nullable=True)
    mentions = Column(JSON, nullable=False, default=list)  # list[str] of user ids
    created_at = Column(DateTime, nullable=False, default=_now)
    edited_at = Column(DateTime, nullable=True)

    issue = relationship("Issue", back_populates="comments")
    author = relationship("User")
    parent = relationship("Comment", remote_side=[id])
