"""Issue service - the single source of truth for issue mutations.

All paths (REST API, MCP tools, scenario scripts) call functions in this
module. Every mutation writes a row to `activities`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.clock import now as _now
from app.models import (
    Comment,
    Issue,
    IssueLabel,
    IssueLink,
    Label,
    Project,
    Sprint,
    SprintIssue,
    User,
    Watcher,
    WorkflowStatus,
)
from app.services import history, permissions, workflows


# ---- Reads ----------------------------------------------------------------


def get_issue(db: Session, issue_id: str) -> Issue:
    issue = db.query(Issue).filter(Issue.id == issue_id).one_or_none()
    if issue is None:
        raise HTTPException(status_code=404, detail=f"Issue '{issue_id}' not found.")
    return issue


def list_issues_for_project(db: Session, project_key: str, *, limit: int = 100, offset: int = 0) -> list[Issue]:
    return (
        db.query(Issue)
        .filter(Issue.project_key == project_key)
        .order_by(Issue.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


# ---- Create ---------------------------------------------------------------


@dataclass
class CreateIssueInput:
    project_key: str
    issue_type: str
    summary: str
    description: Optional[str] = None
    priority: str = "Medium"
    owner: Optional[str] = None
    story_points: Optional[int] = None
    labels: list[str] | None = None
    parent_id: Optional[str] = None
    epic_id: Optional[str] = None


def create_issue(db: Session, actor: User, payload: CreateIssueInput) -> Issue:
    permissions.require(db, actor, "issue.create", project_key=payload.project_key)

    project = db.query(Project).filter(Project.key == payload.project_key).one_or_none()
    if project is None:
        raise HTTPException(404, f"Project {payload.project_key} not found.")

    if payload.issue_type not in _VALID_ISSUE_TYPES:
        raise HTTPException(422, f"Unknown issue_type '{payload.issue_type}'.")
    if payload.priority not in _VALID_PRIORITIES:
        raise HTTPException(422, f"Unknown priority '{payload.priority}'.")

    # ID + counter increment (commit via flush at end)
    n = project.next_issue_number
    issue_id = f"{project.key}-{n}"
    project.next_issue_number = n + 1

    initial_status = workflows.initial_status_for_project(db, project.key)

    issue = Issue(
        id=issue_id,
        project_key=project.key,
        issue_type=payload.issue_type,
        summary=payload.summary,
        description=payload.description,
        status_id=initial_status.id,
        board_list=initial_status.board_list,
        priority=payload.priority,
        owner=payload.owner,
        reporter=actor.id,
        story_points=payload.story_points,
        parent_id=payload.parent_id,
        epic_id=payload.epic_id,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(issue)
    db.flush()

    for lbl in payload.labels or []:
        _ensure_label(db, lbl)
        db.add(IssueLabel(issue_id=issue.id, label_name=lbl))

    history.issue_created(db, actor.id, issue.id, issue.summary)
    if payload.owner:
        history.issue_assigned(db, actor.id, issue.id, None, payload.owner)
    # Treat @mentions in the description like @mentions in a comment so the
    # notifications feed catches people tagged at issue-creation time. Mirrors
    # Jira behaviour: typing `@priya please own this` in the body delivers a
    # notification just like a comment does.
    for mentioned_id in extract_mentions(db, payload.description or ""):
        if mentioned_id == actor.id:
            continue
        history.issue_mentioned(db, actor.id, issue.id, mentioned_id, payload.description or "")
    db.flush()
    return issue


# ---- Update ---------------------------------------------------------------


# Editable fields whitelist - patch keys outside this set are rejected.
# Owner/assignee has its own endpoint (assign_issue); sprint has set_sprint;
# labels have add_label / remove_label. Everything else flows through here.
_EDITABLE_FIELDS = {
    "summary", "description", "priority", "story_points",
    "due_date", "parent_id", "epic_id", "resolution",
    "reporter", "issue_type",
}

_VALID_PRIORITIES = ("Lowest", "Low", "Medium", "High", "Highest")
_VALID_ISSUE_TYPES = ("Story", "Task", "Bug", "Epic", "Subtask", "Incident", "Spike")


def update_issue(db: Session, actor: User, issue_id: str, patch: dict[str, Any]) -> Issue:
    issue = get_issue(db, issue_id)
    permissions.require(db, actor, "issue.update", project_key=issue.project_key)

    unknown = set(patch.keys()) - _EDITABLE_FIELDS
    if unknown:
        raise HTTPException(422, f"Cannot update field(s): {sorted(unknown)}. "
                                  f"Allowed: {sorted(_EDITABLE_FIELDS)}.")

    # Per-field validation. Each branch keeps the same error shape so REST and
    # MCP show identical messages.
    if "priority" in patch and patch["priority"] not in _VALID_PRIORITIES:
        raise HTTPException(
            422,
            f"Unknown priority '{patch['priority']}'. Valid: {list(_VALID_PRIORITIES)}.",
        )
    if "issue_type" in patch and patch["issue_type"] not in _VALID_ISSUE_TYPES:
        raise HTTPException(
            422,
            f"Unknown issue_type '{patch['issue_type']}'. Valid: {list(_VALID_ISSUE_TYPES)}.",
        )
    if "reporter" in patch and patch["reporter"] is not None:
        if db.query(User).filter(User.id == patch["reporter"]).one_or_none() is None:
            raise HTTPException(404, f"Reporter '{patch['reporter']}' is not a known user.")
    if "story_points" in patch and patch["story_points"] is not None:
        try:
            sp = int(patch["story_points"])
        except (TypeError, ValueError):
            raise HTTPException(422, "story_points must be an integer or null.") from None
        if sp < 0 or sp > 1000:
            raise HTTPException(422, "story_points must be between 0 and 1000.")
        patch["story_points"] = sp
    if "parent_id" in patch and patch["parent_id"] is not None:
        if patch["parent_id"] == issue.id:
            raise HTTPException(422, "An issue cannot be its own parent.")
        if db.query(Issue).filter(Issue.id == patch["parent_id"]).one_or_none() is None:
            raise HTTPException(404, f"Parent issue '{patch['parent_id']}' not found.")
    if "epic_id" in patch and patch["epic_id"] is not None:
        epic = db.query(Issue).filter(Issue.id == patch["epic_id"]).one_or_none()
        if epic is None:
            raise HTTPException(404, f"Epic '{patch['epic_id']}' not found.")
        if epic.issue_type != "Epic":
            raise HTTPException(422, f"Issue '{patch['epic_id']}' is not an Epic.")
    # Date coercion: REST goes through Pydantic which gives us a `date` already,
    # but MCP tools accept plain JSON so `due_date` arrives as a string. Coerce
    # here so both surfaces converge before we hit SQLAlchemy (which is strict
    # about `date` vs `str`).
    if "due_date" in patch and patch["due_date"] is not None:
        v = patch["due_date"]
        if isinstance(v, str):
            from datetime import date as _date
            try:
                patch["due_date"] = _date.fromisoformat(v)
            except ValueError as e:
                raise HTTPException(422, f"Invalid due_date '{v}': expected YYYY-MM-DD.") from None

    # Capture the previous description BEFORE we mutate so we can diff
    # @mentions and only notify users who weren't already tagged. Without
    # this, editing the description for a typo would re-notify everyone.
    previous_description = issue.description if "description" in patch else None

    for field, new_value in patch.items():
        old_value = getattr(issue, field)
        if old_value == new_value:
            continue
        setattr(issue, field, new_value)
        history.issue_updated(db, actor.id, issue.id, field, old_value, new_value)

    if "description" in patch:
        old_mentions = set(extract_mentions(db, previous_description or ""))
        new_mentions = set(extract_mentions(db, issue.description or ""))
        for mentioned_id in new_mentions - old_mentions:
            if mentioned_id == actor.id:
                continue
            history.issue_mentioned(db, actor.id, issue.id, mentioned_id, issue.description or "")

    issue.updated_at = _now()
    db.flush()
    return issue


# ---- Sprint membership ----------------------------------------------------


def set_sprint(db: Session, actor: User, issue_id: str, sprint_id: Optional[str]) -> Issue:
    """Move an issue to `sprint_id`, or pull it back to the backlog when None.

    This is what the UI's sprint picker calls. The lower-level
    `sprints.add_issues_to_sprint` / `remove_issues_from_sprint` services are
    still used for bulk operations; this one just provides a 1-issue idiom.
    """
    from app.services.sprints import add_issues_to_sprint, remove_issues_from_sprint

    issue = get_issue(db, issue_id)
    permissions.require(db, actor, "issue.update", project_key=issue.project_key)

    current = (
        db.query(SprintIssue, Sprint)
        .join(Sprint, Sprint.id == SprintIssue.sprint_id)
        .filter(SprintIssue.issue_id == issue.id, Sprint.project_key == issue.project_key)
        .one_or_none()
    )

    if sprint_id is None:
        if current is not None:
            remove_issues_from_sprint(db, actor, current[1].id, [issue.id])
        return issue

    target = db.query(Sprint).filter(Sprint.id == sprint_id).one_or_none()
    if target is None:
        raise HTTPException(404, f"Sprint '{sprint_id}' not found.")
    if target.project_key != issue.project_key:
        raise HTTPException(
            422,
            f"Sprint '{sprint_id}' is in project {target.project_key}, "
            f"issue {issue.id} is in {issue.project_key}.",
        )
    add_issues_to_sprint(db, actor, target.id, [issue.id])
    db.flush()
    return issue


# ---- Transition -----------------------------------------------------------


def transition_issue(
    db: Session, actor: User, issue_id: str, to_status: str, comment_body: Optional[str] = None
) -> Issue:
    issue = get_issue(db, issue_id)
    permissions.require(db, actor, "issue.transition", project_key=issue.project_key)

    transition, target = workflows.find_transition_by_target(db, issue, to_status)
    workflows.evaluate_guards(db, issue, transition, target)

    from_status_name = (
        db.query(WorkflowStatus).filter(WorkflowStatus.id == issue.status_id).one().name
    )
    issue.status_id = target.id
    issue.board_list = target.board_list
    issue.updated_at = _now()
    # Auto-set resolution when entering a Done-category status if unset
    if target.category == "done" and not issue.resolution:
        issue.resolution = "Fixed"
    if target.category != "done" and issue.resolution:
        issue.resolution = None

    history.issue_transitioned(db, actor.id, issue.id, from_status_name, target.name)
    if comment_body:
        add_comment(db, actor, issue.id, comment_body)
    db.flush()
    return issue


# ---- Assign ---------------------------------------------------------------


def assign_issue(db: Session, actor: User, issue_id: str, assignee: Optional[str]) -> Issue:
    issue = get_issue(db, issue_id)
    permissions.require(db, actor, "issue.assign", project_key=issue.project_key)
    if assignee is not None:
        target = db.query(User).filter(User.id == assignee).one_or_none()
        if target is None:
            raise HTTPException(404, f"User '{assignee}' not found.")
    old = issue.owner
    if old == assignee:
        return issue
    issue.owner = assignee
    issue.updated_at = _now()
    history.issue_assigned(db, actor.id, issue.id, old, assignee)
    db.flush()
    return issue


# ---- Comments -------------------------------------------------------------


def add_comment(db: Session, actor: User, issue_id: str, body: str, *, parent_comment_id: Optional[str] = None) -> Comment:
    issue = get_issue(db, issue_id)
    permissions.require(db, actor, "comment.add")
    if not body or not body.strip():
        raise HTTPException(422, "Comment body cannot be empty.")

    # Parse @mentions out of the body now so reads (notifications feed, JQL
    # 'text ~ "@me"', etc.) don't have to re-tokenize the markdown each time.
    mentions = extract_mentions(db, body)

    comment = Comment(
        id=f"comment_{issue.id}_{_now().timestamp():.6f}",
        issue_id=issue.id,
        author_id=actor.id,
        body=body,
        parent_comment_id=parent_comment_id,
        mentions=mentions,
        created_at=_now(),
    )
    db.add(comment)
    db.flush()
    history.issue_commented(db, actor.id, issue.id, body)

    # Emit one activity per mention so the notifications feed is just a query
    # against `activities` and so the audit log shows who got tagged when.
    # Skip self-mentions; they don't generate notifications.
    for mentioned_id in mentions:
        if mentioned_id == actor.id:
            continue
        history.issue_mentioned(db, actor.id, issue.id, mentioned_id, body)
    db.flush()
    return comment


import re as _re

# Comments accept two flavors of @mention. Both resolve to a user id stored in
# `comments.mentions` and emit a `mentioned` activity:
#   1. `@user_<id>`     canonical, what agents should prefer
#   2. `@first_last`    lowercase snake-case (matches a user id suffix). The
#                       lookup also accepts `@Sarah.Kim`, `@sarah-kim`, etc.
# Spaces terminate the handle, so `@sarah please review` only mentions "sarah".
_MENTION_RE = _re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z][A-Za-z0-9_.\-]{0,40})")


def extract_mentions(db: Session, body: str) -> list[str]:
    """Parse @mention tokens in `body` into a deduplicated list of user ids.

    Unknown handles are silently skipped (matches Jira's UX: typing @nobody
    isn't a hard error).
    """
    if not body or "@" not in body:
        return []

    out: list[str] = []
    seen: set[str] = set()

    # Cache the user table once per call to avoid N round-trips on long comments.
    users = db.query(User).all()
    by_id = {u.id: u for u in users}
    by_id_suffix = {u.id.removeprefix("user_"): u for u in users}

    for raw in _MENTION_RE.findall(body):
        # Strip trailing punctuation (e.g. "@sarah_kim,") that the regex doesn't
        # know how to peel off without going non-greedy.
        handle = raw.strip().rstrip(".,;:!?")
        if not handle:
            continue
        normalized = handle.lower().replace("-", "_").replace(".", "_")
        u = by_id.get(handle) or by_id_suffix.get(normalized)
        if u is None:
            continue
        if u.id not in seen:
            seen.add(u.id)
            out.append(u.id)
    return out


def list_comments(db: Session, issue_id: str) -> list[Comment]:
    get_issue(db, issue_id)
    return (
        db.query(Comment)
        .filter(Comment.issue_id == issue_id)
        .order_by(Comment.created_at)
        .all()
    )


def _get_comment(db: Session, issue_id: str, comment_id: str) -> Comment:
    get_issue(db, issue_id)
    c = db.query(Comment).filter(Comment.id == comment_id).one_or_none()
    if c is None or c.issue_id != issue_id:
        raise HTTPException(404, f"Comment '{comment_id}' not found on issue '{issue_id}'.")
    return c


def update_comment(db: Session, actor: User, issue_id: str, comment_id: str, body: str) -> Comment:
    """Edit a comment body. Only the author or an admin can edit.

    On edit we re-parse @mentions and emit `mentioned` activities for any
    users newly tagged (same diff rule as description edits — editing a typo
    won't spam the original recipients).
    """
    if not body or not body.strip():
        raise HTTPException(422, "Comment body cannot be empty.")
    comment = _get_comment(db, issue_id, comment_id)
    if comment.author_id != actor.id and actor.role != "admin":
        raise HTTPException(403, "Only the comment author or an admin can edit a comment.")

    old_body = comment.body
    if old_body == body:
        return comment

    old_mentions = set(comment.mentions or [])
    new_mentions = extract_mentions(db, body)
    comment.body = body
    comment.mentions = new_mentions
    comment.edited_at = _now()

    history.comment_edited(db, actor.id, issue_id, comment.id, old_body, body)
    for mentioned_id in set(new_mentions) - old_mentions:
        if mentioned_id == actor.id:
            continue
        history.issue_mentioned(db, actor.id, issue_id, mentioned_id, body)
    db.flush()
    return comment


def delete_comment(db: Session, actor: User, issue_id: str, comment_id: str) -> None:
    """Delete a comment. Only the author or an admin can delete.

    We preserve the audit row (`comment_deleted` with the old body in
    `from_value`) so deletions are reversible if you read the history.
    """
    comment = _get_comment(db, issue_id, comment_id)
    if comment.author_id != actor.id and actor.role != "admin":
        raise HTTPException(403, "Only the comment author or an admin can delete a comment.")
    body = comment.body
    db.delete(comment)
    history.comment_deleted(db, actor.id, issue_id, comment.id, body)
    db.flush()


# ---- Links ----------------------------------------------------------------


def link_issues(db: Session, actor: User, source_id: str, target_id: str, link_type: str) -> IssueLink:
    if source_id == target_id:
        raise HTTPException(422, "Cannot link an issue to itself.")
    if link_type not in ("blocks", "relates", "duplicates", "clones", "causes"):
        raise HTTPException(422, f"Unknown link_type '{link_type}'.")
    src = get_issue(db, source_id)
    tgt = get_issue(db, target_id)
    permissions.require(db, actor, "issue.link", project_key=src.project_key)
    # idempotent
    existing = (
        db.query(IssueLink)
        .filter(
            IssueLink.source_id == source_id,
            IssueLink.target_id == target_id,
            IssueLink.link_type == link_type,
        )
        .one_or_none()
    )
    if existing:
        return existing
    link = IssueLink(
        id=f"link_{src.id}_{tgt.id}_{link_type}_{_now().timestamp():.0f}",
        source_id=source_id, target_id=target_id, link_type=link_type,
        created_at=_now(),
    )
    db.add(link)
    history.issue_linked(db, actor.id, source_id, target_id, link_type)
    db.flush()
    return link


def unlink_issues(db: Session, actor: User, source_id: str, target_id: str, link_type: str) -> None:
    src = get_issue(db, source_id)
    permissions.require(db, actor, "issue.link", project_key=src.project_key)
    link = (
        db.query(IssueLink)
        .filter(
            IssueLink.source_id == source_id,
            IssueLink.target_id == target_id,
            IssueLink.link_type == link_type,
        )
        .one_or_none()
    )
    if link is None:
        return
    db.delete(link)
    history.issue_unlinked(db, actor.id, source_id, target_id, link_type)
    db.flush()


# ---- Labels / watchers ----------------------------------------------------


def add_label(db: Session, actor: User, issue_id: str, label: str) -> Issue:
    issue = get_issue(db, issue_id)
    permissions.require(db, actor, "issue.update", project_key=issue.project_key)
    _ensure_label(db, label)
    existing = (
        db.query(IssueLabel)
        .filter(IssueLabel.issue_id == issue_id, IssueLabel.label_name == label)
        .one_or_none()
    )
    if existing is None:
        db.add(IssueLabel(issue_id=issue_id, label_name=label))
        history.issue_labeled(db, actor.id, issue_id, label)
        issue.updated_at = _now()
        db.flush()
    return issue


def remove_label(db: Session, actor: User, issue_id: str, label: str) -> Issue:
    issue = get_issue(db, issue_id)
    permissions.require(db, actor, "issue.update", project_key=issue.project_key)
    existing = (
        db.query(IssueLabel)
        .filter(IssueLabel.issue_id == issue_id, IssueLabel.label_name == label)
        .one_or_none()
    )
    if existing:
        db.delete(existing)
        history.issue_unlabeled(db, actor.id, issue_id, label)
        issue.updated_at = _now()
        db.flush()
    return issue


def watch_issue(db: Session, actor: User, issue_id: str) -> Issue:
    issue = get_issue(db, issue_id)
    existing = (
        db.query(Watcher)
        .filter(Watcher.issue_id == issue_id, Watcher.user_id == actor.id)
        .one_or_none()
    )
    if existing is None:
        db.add(Watcher(issue_id=issue_id, user_id=actor.id, created_at=_now()))
        history.issue_watched(db, actor.id, issue_id)
        db.flush()
    return issue


def unwatch_issue(db: Session, actor: User, issue_id: str) -> Issue:
    issue = get_issue(db, issue_id)
    existing = (
        db.query(Watcher)
        .filter(Watcher.issue_id == issue_id, Watcher.user_id == actor.id)
        .one_or_none()
    )
    if existing:
        db.delete(existing)
        history.issue_unwatched(db, actor.id, issue_id)
        db.flush()
    return issue


# ---- Helpers --------------------------------------------------------------


def _ensure_label(db: Session, name: str) -> None:
    if db.query(Label).filter(Label.name == name).one_or_none() is None:
        db.add(Label(name=name))
        db.flush()
