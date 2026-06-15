"""Issue routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api._helpers import history_for_issue, issue_to_detail, issue_to_out
from app.auth import get_current_user
from app.db import get_session
from app.models import User
from app.schemas.api import (
    ActivityOut,
    CommentOut,
    IssueAssignIn,
    IssueCommentIn,
    IssueCreateIn,
    IssueDetailOut,
    IssueLabelIn,
    IssueLinkIn,
    IssueLinkOut,
    IssueOut,
    IssuePatchIn,
    IssueSprintIn,
    IssueTransitionIn,
)
from app.services import issues as issue_svc

router = APIRouter()


@router.get("/{issue_id}", response_model=IssueDetailOut)
def get_issue(
    issue_id: str,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    return issue_to_detail(db, issue_svc.get_issue(db, issue_id))


@router.post("", response_model=IssueDetailOut, status_code=201)
def create_issue(
    payload: IssueCreateIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    issue = issue_svc.create_issue(db, user, issue_svc.CreateIssueInput(**payload.model_dump()))
    db.commit()
    return issue_to_detail(db, issue)


@router.patch("/{issue_id}", response_model=IssueDetailOut)
def patch_issue(
    issue_id: str,
    payload: IssuePatchIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    issue = issue_svc.update_issue(db, user, issue_id, payload.model_dump(exclude_unset=True))
    db.commit()
    return issue_to_detail(db, issue)


@router.post("/{issue_id}/transitions", response_model=IssueDetailOut)
def transition_issue(
    issue_id: str,
    payload: IssueTransitionIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    issue = issue_svc.transition_issue(db, user, issue_id, payload.to_status, payload.comment)
    db.commit()
    return issue_to_detail(db, issue)


@router.post("/{issue_id}/assign", response_model=IssueDetailOut)
def assign_issue(
    issue_id: str,
    payload: IssueAssignIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    issue = issue_svc.assign_issue(db, user, issue_id, payload.assignee)
    db.commit()
    return issue_to_detail(db, issue)


@router.put("/{issue_id}/sprint", response_model=IssueDetailOut)
def set_sprint(
    issue_id: str,
    payload: IssueSprintIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    """Move an issue to a sprint, or pull it back to the backlog with `null`."""
    issue = issue_svc.set_sprint(db, user, issue_id, payload.sprint_id)
    db.commit()
    return issue_to_detail(db, issue)


@router.post("/{issue_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(
    issue_id: str,
    payload: IssueCommentIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    c = issue_svc.add_comment(db, user, issue_id, payload.body, parent_comment_id=payload.parent_comment_id)
    db.commit()
    return CommentOut.model_validate(c)


@router.get("/{issue_id}/comments", response_model=list[CommentOut])
def list_comments(
    issue_id: str,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    return [CommentOut.model_validate(c) for c in issue_svc.list_comments(db, issue_id)]


@router.patch("/{issue_id}/comments/{comment_id}", response_model=CommentOut)
def update_comment(
    issue_id: str,
    comment_id: str,
    payload: IssueCommentIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    """Edit an existing comment. Only the author or an admin may edit."""
    c = issue_svc.update_comment(db, user, issue_id, comment_id, payload.body)
    db.commit()
    return CommentOut.model_validate(c)


@router.delete("/{issue_id}/comments/{comment_id}", status_code=204)
def delete_comment(
    issue_id: str,
    comment_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    """Delete a comment. Only the author or an admin may delete."""
    issue_svc.delete_comment(db, user, issue_id, comment_id)
    db.commit()


@router.post("/{issue_id}/links", response_model=IssueLinkOut, status_code=201)
def add_link(
    issue_id: str,
    payload: IssueLinkIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    link = issue_svc.link_issues(db, user, issue_id, payload.target, payload.link_type)
    db.commit()
    return IssueLinkOut.model_validate(link)


@router.delete("/{issue_id}/links", status_code=204)
def remove_link(
    issue_id: str,
    payload: IssueLinkIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    issue_svc.unlink_issues(db, user, issue_id, payload.target, payload.link_type)
    db.commit()


@router.post("/{issue_id}/labels", response_model=IssueDetailOut)
def add_label(
    issue_id: str,
    payload: IssueLabelIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    issue = issue_svc.add_label(db, user, issue_id, payload.label)
    db.commit()
    return issue_to_detail(db, issue)


@router.delete("/{issue_id}/labels/{label}", response_model=IssueDetailOut)
def remove_label(
    issue_id: str,
    label: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    issue = issue_svc.remove_label(db, user, issue_id, label)
    db.commit()
    return issue_to_detail(db, issue)


@router.post("/{issue_id}/watch", response_model=IssueDetailOut)
def watch(
    issue_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    issue = issue_svc.watch_issue(db, user, issue_id)
    db.commit()
    return issue_to_detail(db, issue)


@router.delete("/{issue_id}/watch", response_model=IssueDetailOut)
def unwatch(
    issue_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    issue = issue_svc.unwatch_issue(db, user, issue_id)
    db.commit()
    return issue_to_detail(db, issue)


@router.get("/{issue_id}/history", response_model=list[ActivityOut])
def get_history(
    issue_id: str,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    limit: int = 50,
):
    return [ActivityOut.model_validate(a) for a in history_for_issue(db, issue_id, limit)]
