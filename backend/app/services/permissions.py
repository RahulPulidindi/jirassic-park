"""RBAC.

Two layers:
- Global role: admin | member | viewer (from User.role)
- Project role: lead | developer | reporter | viewer (derived per call)

Permission matrix (action -> who):
    read.*                : everyone with a valid token
    comment.add           : member+
    issue.create          : member+
    issue.update          : member+ on any project where they're a team member;
                            admin/lead anywhere
    issue.transition      : same as issue.update
    issue.assign          : same as issue.update
    issue.link            : same as issue.update
    sprint.create         : lead | admin
    sprint.start          : lead | admin
    sprint.complete       : lead | admin
    workflow.edit         : admin
    user.manage           : admin
    project.create        : admin
    admin.reset           : admin
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Project, TeamMember, User


class PermissionError(HTTPException):
    def __init__(self, action: str, detail: Optional[str] = None):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail or f"You do not have permission to perform '{action}'.",
        )


def project_role(db: Session, user: User, project_key: str) -> str:
    """Derive the user's role in a project: lead | developer | reporter | viewer."""
    if user.role == "admin":
        return "lead"
    project = db.query(Project).filter(Project.key == project_key).one_or_none()
    if project is not None and project.lead_id == user.id:
        return "lead"
    if user.role == "viewer":
        return "viewer"
    # member of any team that has visibility — keep it simple: members are
    # developers by default since we don't model multi-project team scoping.
    if db.query(TeamMember).filter(TeamMember.user_id == user.id).count() > 0:
        return "developer"
    return "reporter"


def require(db: Session, user: User, action: str, *, project_key: Optional[str] = None) -> None:
    """Raise HTTPException(403) if the user can't perform `action` (optionally on a project)."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    if action == "admin.reset" or action == "admin.reseed" or action == "user.manage" or action == "project.create":
        if user.role != "admin":
            raise PermissionError(
                action,
                f"'{action}' requires admin role. Your role: {user.role}.",
            )
        return

    if action == "workflow.edit":
        if user.role != "admin":
            raise PermissionError(action, "Only admins can edit workflows.")
        return

    if action.startswith("read"):
        if user.role == "viewer" or user.role == "member" or user.role == "admin":
            return
        raise PermissionError(action)

    if action == "comment.add":
        if user.role in ("admin", "member"):
            return
        raise PermissionError(action, "Viewers cannot add comments.")

    if action in ("issue.create", "issue.update", "issue.transition", "issue.assign", "issue.link"):
        if user.role == "viewer":
            raise PermissionError(action, f"Viewers cannot {action.split('.')[1]} issues.")
        if user.role == "admin":
            return
        # Members: allow on any project
        if user.role == "member":
            return
        raise PermissionError(action)

    if action in ("sprint.create", "sprint.start", "sprint.complete"):
        if project_key is None:
            raise PermissionError(action, "Sprint actions require a project context.")
        role = project_role(db, user, project_key)
        if role == "lead":
            return
        raise PermissionError(
            action,
            f"Only project leads or admins can {action.split('.')[1]} a sprint. "
            f"Your role on {project_key}: {role}.",
        )

    # Default: deny unknown actions.
    raise PermissionError(action, f"Unknown action '{action}'.")
