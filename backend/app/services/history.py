"""Audit log writer.

Every mutation in the services layer should call exactly one of the helper
functions below. Activities are what powers the issue history tab, recent
activity feeds, and the admin audit view.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.clock import now as _now
from app.models import Activity


def _act(
    db: Session,
    *,
    actor_id: str,
    action: str,
    entity_type: str = "issue",
    entity_id: str,
    issue_id: Optional[str] = None,
    field: Optional[str] = None,
    from_value: Optional[str] = None,
    to_value: Optional[str] = None,
    comment_body: Optional[str] = None,
) -> Activity:
    activity = Activity(
        id=f"act_{uuid.uuid4().hex[:16]}",
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        issue_id=issue_id or (entity_id if entity_type == "issue" else None),
        action=action,
        field=field,
        from_value=from_value,
        to_value=to_value,
        comment_body=comment_body,
        created_at=_now(),
    )
    db.add(activity)
    return activity


def issue_created(db, actor_id: str, issue_id: str, summary: str) -> Activity:
    return _act(db, actor_id=actor_id, action="created", entity_id=issue_id, to_value=summary)


def issue_updated(db, actor_id: str, issue_id: str, field: str, from_value, to_value) -> Activity:
    return _act(
        db, actor_id=actor_id, action="updated", entity_id=issue_id,
        field=field, from_value=_str(from_value), to_value=_str(to_value),
    )


def issue_transitioned(db, actor_id: str, issue_id: str, from_status: str, to_status: str) -> Activity:
    return _act(
        db, actor_id=actor_id, action="transitioned", entity_id=issue_id,
        field="status", from_value=from_status, to_value=to_status,
    )


def issue_assigned(db, actor_id: str, issue_id: str, from_user: Optional[str], to_user: Optional[str]) -> Activity:
    return _act(
        db, actor_id=actor_id, action="assigned", entity_id=issue_id,
        field="owner", from_value=from_user, to_value=to_user,
    )


def issue_commented(db, actor_id: str, issue_id: str, body: str) -> Activity:
    return _act(db, actor_id=actor_id, action="commented", entity_id=issue_id, comment_body=body)


def comment_edited(db, actor_id: str, issue_id: str, comment_id: str, old_body: str, new_body: str) -> Activity:
    """Emit one row per comment edit. `entity_id` is the comment id so we can
    link audit rows back to the specific comment, but `issue_id` is set so the
    issue history feed still surfaces it."""
    return _act(
        db, actor_id=actor_id, action="comment_edited",
        entity_type="comment", entity_id=comment_id, issue_id=issue_id,
        field="body", from_value=old_body, to_value=new_body,
    )


def comment_deleted(db, actor_id: str, issue_id: str, comment_id: str, body: str) -> Activity:
    return _act(
        db, actor_id=actor_id, action="comment_deleted",
        entity_type="comment", entity_id=comment_id, issue_id=issue_id,
        from_value=body,
    )


def issue_mentioned(db, actor_id: str, issue_id: str, mentioned_user_id: str, body: str) -> Activity:
    """One row per mentioned user. `to_value` is the mentioned user id so the
    notifications feed is just `WHERE action='mentioned' AND to_value=<me>`."""
    return _act(
        db, actor_id=actor_id, action="mentioned", entity_id=issue_id,
        field="mention", to_value=mentioned_user_id, comment_body=body,
    )


def issue_linked(db, actor_id: str, source_id: str, target_id: str, link_type: str) -> Activity:
    return _act(
        db, actor_id=actor_id, action="linked", entity_id=source_id,
        field="link", to_value=f"{link_type}:{target_id}",
    )


def issue_unlinked(db, actor_id: str, source_id: str, target_id: str, link_type: str) -> Activity:
    return _act(
        db, actor_id=actor_id, action="unlinked", entity_id=source_id,
        field="link", from_value=f"{link_type}:{target_id}",
    )


def issue_labeled(db, actor_id: str, issue_id: str, label: str) -> Activity:
    return _act(db, actor_id=actor_id, action="labeled", entity_id=issue_id, to_value=label, field="label")


def issue_unlabeled(db, actor_id: str, issue_id: str, label: str) -> Activity:
    return _act(db, actor_id=actor_id, action="unlabeled", entity_id=issue_id, from_value=label, field="label")


def issue_watched(db, actor_id: str, issue_id: str) -> Activity:
    return _act(db, actor_id=actor_id, action="watched", entity_id=issue_id)


def issue_unwatched(db, actor_id: str, issue_id: str) -> Activity:
    return _act(db, actor_id=actor_id, action="unwatched", entity_id=issue_id)


def sprint_added(db, actor_id: str, issue_id: str, sprint_id: str) -> Activity:
    return _act(
        db, actor_id=actor_id, action="sprint_added", entity_id=issue_id,
        field="sprint", to_value=sprint_id,
    )


def sprint_removed(db, actor_id: str, issue_id: str, sprint_id: str) -> Activity:
    return _act(
        db, actor_id=actor_id, action="sprint_removed", entity_id=issue_id,
        field="sprint", from_value=sprint_id,
    )


def sprint_started(db, actor_id: str, sprint_id: str, name: str) -> Activity:
    return _act(
        db, actor_id=actor_id, action="sprint_started", entity_type="sprint",
        entity_id=sprint_id, to_value=name,
    )


def sprint_completed(db, actor_id: str, sprint_id: str, name: str) -> Activity:
    return _act(
        db, actor_id=actor_id, action="sprint_completed", entity_type="sprint",
        entity_id=sprint_id, to_value=name,
    )


def env_reset(db, actor_id: str) -> Activity:
    return _act(
        db, actor_id=actor_id, action="reset", entity_type="env",
        entity_id="env", to_value="reset_to_seed",
    )


def _str(v) -> Optional[str]:
    if v is None:
        return None
    return str(v)
