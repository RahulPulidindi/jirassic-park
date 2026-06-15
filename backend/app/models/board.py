"""Board model. Boards filter and group issues for visual display."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.clock import now as _now
from app.db import Base


class Board(Base):
    __tablename__ = "boards"

    id = Column(String, primary_key=True)
    project_key = Column(String, ForeignKey("projects.key"), nullable=False)
    name = Column(String, nullable=False)
    board_type = Column(String, nullable=False, default="scrum")  # scrum | kanban
    filter_jql = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)

    project = relationship("Project", back_populates="boards")
