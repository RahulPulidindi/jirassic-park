"""User and team models."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.clock import now as _now
from app.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)  # e.g. "user_sarah_kim"
    email = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    avatar_color = Column(String, nullable=False, default="#5d6a99")
    role = Column(String, nullable=False, default="member")  # admin | member | viewer
    api_token = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    team_memberships = relationship("TeamMember", back_populates="user", cascade="all, delete-orphan")


class Team(Base):
    __tablename__ = "teams"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    memberships = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)

    team_id = Column(String, ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role = Column(String, nullable=False, default="member")  # lead | member

    team = relationship("Team", back_populates="memberships")
    user = relationship("User", back_populates="team_memberships")
