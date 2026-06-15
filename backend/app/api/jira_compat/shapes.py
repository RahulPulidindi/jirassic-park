"""Projection functions: Jirassic Park ORM rows -> Atlassian-shaped JSON.

Every public function here returns a plain dict whose keys, nesting, and value
types match Atlassian REST v3's `GET /rest/api/3/...` response shape. We strive
to keep value *types* (string vs object vs list) exact even when the underlying
value (numeric id, accountId, ADF body) is a fabrication.

Documented simplifications are listed at the bottom of this file and tracked
in `backend/tests/fixtures/real_jira/expected_diffs.yaml`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.api._helpers import labels_for_issue, sprint_for_issue, watchers_for_issue
from app.api.jira_compat.ids import (
    account_id_for,
    numeric_id_for_comment,
    numeric_id_for_issue,
    numeric_id_for_issuetype,
    numeric_id_for_link,
    numeric_id_for_priority,
    numeric_id_for_project,
    numeric_id_for_status,
)
from app.models import (
    Activity,
    Comment,
    Issue,
    IssueLink,
    Project,
    Sprint,
    SprintIssue,
    User,
    Watcher,
    WorkflowStatus,
)


# ---- Datetimes & ADF -------------------------------------------------------

_JIRA_DT_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


def to_jira_datetime(dt: Optional[datetime]) -> Optional[str]:
    """Format a UTC datetime as Atlassian's ISO-8601 with millisecond
    precision and a -0700-style offset. Real Jira's representative format is:
    `2026-05-15T14:22:00.000-0700`. We emit `+0000` because the DB stores naive
    UTC; the format string is the leverage point for agents that parse
    timestamps with a regex."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # %f gives microseconds; trim to milliseconds.
    formatted = dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"
    offset = dt.utcoffset() or _ZERO_OFFSET
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return f"{formatted}{sign}{total_minutes // 60:02d}{total_minutes % 60:02d}"


from datetime import timedelta
_ZERO_OFFSET = timedelta(0)


def plaintext_to_adf(text: Optional[str]) -> Optional[dict]:
    """Wrap a plaintext body in the minimum valid Atlassian Document Format
    envelope so the shape of `fields.description` and `body` matches what
    real Jira returns. We do not parse Markdown; one paragraph node per
    blank-line block. Agents that traverse ADF will find the same node types
    they expect (`doc` > `paragraph` > `text`)."""
    if text is None:
        return None
    if text == "":
        return {"type": "doc", "version": 1, "content": []}
    paragraphs: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        if not block:
            continue
        paragraphs.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": block}],
        })
    return {"type": "doc", "version": 1, "content": paragraphs}


def adf_to_plaintext(adf: Any) -> Optional[str]:
    """Reverse of plaintext_to_adf for inputs. Real Jira accepts ADF on
    create/edit; we accept either a string or a `{type: doc, ...}` body."""
    if adf is None:
        return None
    if isinstance(adf, str):
        return adf
    if not isinstance(adf, dict) or adf.get("type") != "doc":
        return None
    parts: list[str] = []
    for block in adf.get("content", []) or []:
        if block.get("type") != "paragraph":
            continue
        chunk = "".join(
            child.get("text", "")
            for child in block.get("content", []) or []
            if child.get("type") == "text"
        )
        parts.append(chunk)
    return "\n\n".join(p for p in parts if p)


# ---- References (compact summaries) ----------------------------------------


def _self_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}{path}"


def user_ref(user: Optional[User], *, base_url: str) -> Optional[dict]:
    """Compact user reference object — the same shape used inside
    `fields.assignee`, `fields.reporter`, comment authors, etc."""
    if user is None:
        return None
    aid = account_id_for(user.id)
    return {
        "self": _self_url(base_url, f"/rest/api/3/user?accountId={aid}"),
        "accountId": aid,
        "accountType": "atlassian",
        "emailAddress": user.email,
        "displayName": user.display_name or user.name,
        "active": True,
        "timeZone": "America/Los_Angeles",
        # Real Jira sends a 16x16/24x24/32x32/48x48 PNG bundle. We synthesize
        # data URIs from the user's color so the field shape is correct without
        # serving real images.
        "avatarUrls": _avatar_urls(user.avatar_color),
    }


def _avatar_urls(color: str) -> dict[str, str]:
    """Stable {size: url} object. Values are data URIs to a 1x1 PNG of the
    user's color; agents that care only about the field shape get it."""
    # Tiny opaque-color SVG data URIs (1 line each, deterministic).
    def svg(size: int) -> str:
        return (
            f"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' "
            f"width='{size}' height='{size}'><rect width='{size}' height='{size}' "
            f"fill='{color.lstrip('#')}'/></svg>"
        )
    return {
        "48x48": svg(48),
        "32x32": svg(32),
        "24x24": svg(24),
        "16x16": svg(16),
    }


def status_ref(status: WorkflowStatus, *, base_url: str) -> dict:
    cat = _status_category(status.category)
    sid = numeric_id_for_status(status.id)
    return {
        "self": _self_url(base_url, f"/rest/api/3/status/{sid}"),
        "id": sid,
        "name": status.name,
        "description": "",
        "iconUrl": _self_url(base_url, "/images/icons/statuses/generic.png"),
        "statusCategory": cat,
    }


def _status_category(internal: str) -> dict:
    # Atlassian's well-known statusCategory ids:
    #   1 = No Category, 2 = New (to-do), 3 = Indeterminate (in-progress), 4 = Done
    mapping = {
        "todo": {"id": 2, "key": "new", "name": "To Do", "colorName": "blue-gray"},
        "in_progress": {"id": 4, "key": "indeterminate", "name": "In Progress", "colorName": "yellow"},
        "done": {"id": 3, "key": "done", "name": "Done", "colorName": "green"},
    }
    m = mapping.get(internal, mapping["todo"])
    return {"self": "", **m}


def priority_ref(priority_name: str, *, base_url: str) -> dict:
    pid = numeric_id_for_priority(priority_name)
    return {
        "self": _self_url(base_url, f"/rest/api/3/priority/{pid}"),
        "iconUrl": _self_url(base_url, f"/images/icons/priorities/{priority_name.lower()}.svg"),
        "name": priority_name,
        "id": pid,
    }


def issuetype_ref(issue_type: str, *, base_url: str) -> dict:
    iid = numeric_id_for_issuetype(issue_type)
    return {
        "self": _self_url(base_url, f"/rest/api/3/issuetype/{iid}"),
        "id": iid,
        "description": "",
        "iconUrl": _self_url(base_url, f"/images/icons/issuetypes/{issue_type.lower()}.svg"),
        "name": issue_type,
        "subtask": issue_type == "Subtask",
        "avatarId": int(iid) if iid.isdigit() else 0,
        "hierarchyLevel": 1 if issue_type == "Epic" else (-1 if issue_type == "Subtask" else 0),
    }


def project_ref(project: Project, *, base_url: str) -> dict:
    pid = numeric_id_for_project(project.key)
    return {
        "self": _self_url(base_url, f"/rest/api/3/project/{pid}"),
        "id": pid,
        "key": project.key,
        "name": project.name,
        "projectTypeKey": project.project_type,
        "simplified": True,
        "avatarUrls": _avatar_urls(project.avatar_color),
    }


def comment_ref(c: Comment, db: Session, *, base_url: str) -> dict:
    author = db.query(User).filter(User.id == c.author_id).one_or_none()
    cid = numeric_id_for_comment(c.id)
    return {
        "self": _self_url(base_url, f"/rest/api/3/issue/{c.issue_id}/comment/{cid}"),
        "id": cid,
        "author": user_ref(author, base_url=base_url) or _ghost_user(c.author_id, base_url=base_url),
        "body": plaintext_to_adf(c.body),
        "updateAuthor": user_ref(author, base_url=base_url) or _ghost_user(c.author_id, base_url=base_url),
        "created": to_jira_datetime(c.created_at),
        "updated": to_jira_datetime(c.edited_at or c.created_at),
        "jsdPublic": True,
    }


def _ghost_user(user_id: str, *, base_url: str) -> dict:
    """Stand-in for a deleted user. Real Jira renders a fixed ghost object."""
    aid = account_id_for(user_id)
    return {
        "self": _self_url(base_url, f"/rest/api/3/user?accountId={aid}"),
        "accountId": aid,
        "accountType": "atlassian",
        "displayName": user_id,
        "active": False,
        "avatarUrls": _avatar_urls("#888888"),
    }


# ---- Full issue ------------------------------------------------------------


def issue_to_jira(
    issue: Issue,
    db: Session,
    *,
    base_url: str,
    expand: Optional[list[str]] = None,
) -> dict:
    """Project an issue row into the Atlassian REST v3 issue shape.

    The default response includes the same fields the standard
    `GET /rest/api/3/issue/{key}` returns. `expand` opt-ins (e.g. `changelog`,
    `renderedFields`) inject the corresponding extra blocks."""
    expand = expand or []
    project = db.query(Project).filter(Project.key == issue.project_key).one()
    status = db.query(WorkflowStatus).filter(WorkflowStatus.id == issue.status_id).one()
    assignee = db.query(User).filter(User.id == issue.owner).one_or_none() if issue.owner else None
    reporter = db.query(User).filter(User.id == issue.reporter).one_or_none()
    sprint_id, sprint_name = sprint_for_issue(db, issue.id)
    sprint = db.query(Sprint).filter(Sprint.id == sprint_id).one_or_none() if sprint_id else None
    labels = labels_for_issue(db, issue.id)
    watcher_ids = watchers_for_issue(db, issue.id)

    parent = (
        db.query(Issue).filter(Issue.id == issue.parent_id).one_or_none()
        if issue.parent_id else None
    )
    epic = (
        db.query(Issue).filter(Issue.id == issue.epic_id).one_or_none()
        if issue.epic_id else None
    )

    # Outbound and inbound links combined in `issuelinks` (Jira's convention).
    outbound = [
        _issuelink_outward(l, db, base_url=base_url) for l in issue.outbound_links
    ]
    inbound = [
        _issuelink_inward(l, db, base_url=base_url) for l in issue.inbound_links
    ]

    iid = numeric_id_for_issue(issue.id)
    out = {
        "expand": "renderedFields,names,schema,operations,editmeta,changelog,versionedRepresentations",
        "id": iid,
        "self": _self_url(base_url, f"/rest/api/3/issue/{iid}"),
        "key": issue.id,
        "fields": {
            "summary": issue.summary,
            "issuetype": issuetype_ref(issue.issue_type, base_url=base_url),
            "project": project_ref(project, base_url=base_url),
            "status": status_ref(status, base_url=base_url),
            "priority": priority_ref(issue.priority, base_url=base_url),
            "assignee": user_ref(assignee, base_url=base_url),
            "reporter": user_ref(reporter, base_url=base_url),
            "creator": user_ref(reporter, base_url=base_url),
            "description": plaintext_to_adf(issue.description),
            "labels": labels,
            "created": to_jira_datetime(issue.created_at),
            "updated": to_jira_datetime(issue.updated_at),
            "duedate": issue.due_date.isoformat() if issue.due_date else None,
            "resolution": _resolution_ref(issue.resolution, base_url=base_url),
            "resolutiondate": None,
            "components": [],   # not modeled, but field must exist (empty list)
            "fixVersions": [],
            "versions": [],
            "watches": {
                "self": _self_url(base_url, f"/rest/api/3/issue/{iid}/watchers"),
                "watchCount": len(watcher_ids),
                "isWatching": False,  # populated per-request in router if user known
            },
            "subtasks": _subtasks_for(issue, db, base_url=base_url),
            "issuelinks": outbound + inbound,
            "parent": _issue_brief(parent, db, base_url=base_url) if parent else None,
            "comment": {
                "comments": [
                    comment_ref(c, db, base_url=base_url)
                    for c in sorted(issue.comments, key=lambda c: c.created_at)
                ],
                "self": _self_url(base_url, f"/rest/api/3/issue/{iid}/comment"),
                "maxResults": len(issue.comments),
                "total": len(issue.comments),
                "startAt": 0,
            },
            "worklog": {"worklogs": [], "total": 0, "startAt": 0, "maxResults": 0},
            # Custom fields we choose to expose. Atlassian's customfield_NNNNN
            # naming is preserved for the well-known ones (sprint, story
            # points, epic link) so agents looking for those exact keys find
            # them.
            "customfield_10020": [_sprint_block(sprint)] if sprint else None,  # Sprint
            "customfield_10016": issue.story_points,                              # Story points
            "customfield_10014": epic.id if epic else None,                       # Epic link (key)
            "customfield_10019": _flagged_value(labels),                         # Flagged
        },
    }

    if "changelog" in expand:
        out["changelog"] = _changelog_for(issue, db, base_url=base_url)
    if "renderedFields" in expand:
        out["renderedFields"] = {
            "description": (issue.description or "").replace("\n", "<br/>") if issue.description else "",
        }
    return out


def _resolution_ref(resolution: Optional[str], *, base_url: str) -> Optional[dict]:
    if not resolution:
        return None
    rid = numeric_id_for_priority(f"resolution:{resolution}")  # stable id from name
    return {
        "self": _self_url(base_url, f"/rest/api/3/resolution/{rid}"),
        "id": rid,
        "name": resolution,
        "description": "",
    }


def _subtasks_for(issue: Issue, db: Session, *, base_url: str) -> list[dict]:
    children = db.query(Issue).filter(Issue.parent_id == issue.id).all()
    return [_issue_brief(c, db, base_url=base_url) for c in children]


def _issue_brief(issue: Issue, db: Session, *, base_url: str) -> dict:
    """Compact issue summary used as nested object (subtasks, parent, link
    inward/outward issue, etc.)."""
    status = db.query(WorkflowStatus).filter(WorkflowStatus.id == issue.status_id).one()
    iid = numeric_id_for_issue(issue.id)
    return {
        "id": iid,
        "key": issue.id,
        "self": _self_url(base_url, f"/rest/api/3/issue/{iid}"),
        "fields": {
            "summary": issue.summary,
            "status": status_ref(status, base_url=base_url),
            "priority": priority_ref(issue.priority, base_url=base_url),
            "issuetype": issuetype_ref(issue.issue_type, base_url=base_url),
        },
    }


def _issuelink_outward(link: IssueLink, db: Session, *, base_url: str) -> dict:
    target = db.query(Issue).filter(Issue.id == link.target_id).one()
    return {
        "id": numeric_id_for_link(link.id),
        "self": _self_url(base_url, f"/rest/api/3/issueLink/{numeric_id_for_link(link.id)}"),
        "type": _link_type(link.link_type, base_url=base_url),
        "outwardIssue": _issue_brief(target, db, base_url=base_url),
    }


def _issuelink_inward(link: IssueLink, db: Session, *, base_url: str) -> dict:
    source = db.query(Issue).filter(Issue.id == link.source_id).one()
    return {
        "id": numeric_id_for_link(link.id),
        "self": _self_url(base_url, f"/rest/api/3/issueLink/{numeric_id_for_link(link.id)}"),
        "type": _link_type(link.link_type, base_url=base_url),
        "inwardIssue": _issue_brief(source, db, base_url=base_url),
    }


_LINK_TYPE_INFO = {
    "blocks":     ("Blocks",     "blocks",         "is blocked by"),
    "relates":    ("Relates",    "relates to",     "relates to"),
    "duplicates": ("Duplicate",  "duplicates",     "is duplicated by"),
    "clones":     ("Cloners",    "clones",         "is cloned by"),
    "causes":     ("Problem/Incident", "causes",   "is caused by"),
}


def _link_type(name: str, *, base_url: str) -> dict:
    info = _LINK_TYPE_INFO.get(name, (name.title(), name, name))
    lname, outward, inward = info
    # Same id from name so it's stable.
    lid = numeric_id_for_link(f"type:{name}")
    return {
        "id": lid,
        "name": lname,
        "inward": inward,
        "outward": outward,
        "self": _self_url(base_url, f"/rest/api/3/issueLinkType/{lid}"),
    }


def _sprint_block(sprint: Sprint) -> dict:
    """Compact sprint representation used inside customfield_10020 (Jira
    Software's sprint custom field)."""
    return {
        "id": _int_or_zero(sprint.id),
        "name": sprint.name,
        "state": sprint.state,
        "boardId": 0,
        "goal": sprint.goal,
        "startDate": to_jira_datetime(sprint.start_date),
        "endDate": to_jira_datetime(sprint.end_date),
        "completeDate": to_jira_datetime(sprint.completed_at),
    }


def _int_or_zero(s: str) -> int:
    """Sprint ids are strings here; Jira returns numeric. Best-effort hash."""
    return abs(hash(s)) % 99_999


def _flagged_value(labels: list[str]) -> Optional[list[dict]]:
    """Real Jira's "Impediment" / Flagged custom field is multi-select.
    We surface it as a single option `Impediment` when the "blocked" label
    is present."""
    if "blocked" in [l.lower() for l in labels]:
        return [{"value": "Impediment", "id": "10000"}]
    return None


# ---- Changelog -------------------------------------------------------------


def _changelog_for(issue: Issue, db: Session, *, base_url: str) -> dict:
    """Build a `?expand=changelog` block: list of history entries with field
    changes grouped per Activity row."""
    acts = (
        db.query(Activity)
        .filter(Activity.issue_id == issue.id, Activity.action.in_(("updated", "transitioned", "assigned")))
        .order_by(Activity.created_at.asc())
        .all()
    )
    histories = []
    for a in acts:
        author = db.query(User).filter(User.id == a.actor_id).one_or_none()
        field_name = "status" if a.action == "transitioned" else (
            "assignee" if a.action == "assigned" else (a.field or "unknown")
        )
        histories.append({
            "id": str(_int_or_zero(a.id)),
            "author": user_ref(author, base_url=base_url) or _ghost_user(a.actor_id, base_url=base_url),
            "created": to_jira_datetime(a.created_at),
            "items": [{
                "field": field_name,
                "fieldtype": "jira",
                "fieldId": field_name,
                "from": a.from_value,
                "fromString": a.from_value,
                "to": a.to_value,
                "toString": a.to_value,
            }],
        })
    return {
        "startAt": 0,
        "maxResults": len(histories),
        "total": len(histories),
        "histories": histories,
    }
