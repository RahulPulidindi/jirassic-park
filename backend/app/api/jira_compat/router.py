"""FastAPI router at /rest/api/3/* that serves Atlassian-shaped responses.

Endpoints we implement (full list, ordered by likely agent use):

  Issues
    GET    /rest/api/3/issue/{idOrKey}                         get_issue
    POST   /rest/api/3/issue                                   create_issue
    PUT    /rest/api/3/issue/{idOrKey}                         edit_issue
    DELETE /rest/api/3/issue/{idOrKey}                         delete_issue (no-op, 405-equivalent)
    POST   /rest/api/3/issue/{idOrKey}/assignee                set_assignee
    GET    /rest/api/3/issue/{idOrKey}/transitions             list_transitions
    POST   /rest/api/3/issue/{idOrKey}/transitions             do_transition
    GET    /rest/api/3/issue/{idOrKey}/comment                 list_comments
    POST   /rest/api/3/issue/{idOrKey}/comment                 add_comment
    PUT    /rest/api/3/issue/{idOrKey}/comment/{commentId}     update_comment
    DELETE /rest/api/3/issue/{idOrKey}/comment/{commentId}     delete_comment
    GET    /rest/api/3/issue/{idOrKey}/watchers                list_watchers
    POST   /rest/api/3/issue/{idOrKey}/watchers                add_watcher
    DELETE /rest/api/3/issue/{idOrKey}/watchers                remove_watcher
    PUT    /rest/api/3/issue/{idOrKey}/labels                  edit_labels (add/remove)
    GET    /rest/api/3/issue/{idOrKey}/changelog               changelog

  Issue links
    POST   /rest/api/3/issueLink                               add_link
    DELETE /rest/api/3/issueLink/{linkId}                      remove_link
    GET    /rest/api/3/issueLinkType                           list_link_types

  Search
    GET    /rest/api/3/search                                  search_jql
    POST   /rest/api/3/search                                  search_jql_post

  Projects
    GET    /rest/api/3/project                                 list_projects
    GET    /rest/api/3/project/{key}                           get_project
    GET    /rest/api/3/project/{key}/statuses                  project_statuses

  Users / myself
    GET    /rest/api/3/myself                                  myself
    GET    /rest/api/3/user                                    get_user
    GET    /rest/api/3/user/search                             search_users

  Metadata
    GET    /rest/api/3/priority                                list_priorities
    GET    /rest/api/3/status                                  list_statuses
    GET    /rest/api/3/issuetype                               list_issuetypes
    GET    /rest/api/3/serverInfo                              server_info
    GET    /rest/api/3/field                                   list_fields

These cover the realistic working set an agent needs for triage / sprint
planning / issue creation workflows. Each endpoint delegates to the same
service-layer functions the legacy /api/* endpoints use, so REST/MCP/UI
write to one underlying state.
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.jira_compat import shapes
from app.api.jira_compat.ids import (
    account_id_for,
    numeric_id_for_link,
)
from app.auth import get_current_user
from app.db import get_session
from app.models import (
    Activity,
    Comment,
    Issue,
    IssueLink,
    Project,
    User,
    Watcher,
    WorkflowStatus,
)
from app.services import issues as issue_svc
from app.services import projects as project_svc
from app.services.search import search


router = APIRouter()


def _base_url(req: Request) -> str:
    return str(req.base_url).rstrip("/")


def _resolve_issue_id_or_key(db: Session, id_or_key: str) -> Issue:
    """Real Jira accepts either the numeric id or the key (PLAT-60) on the
    same endpoint. We support the key (canonical) plus the numeric form we
    synthesize via ids.numeric_id_for_issue."""
    # Try by key first (the common case).
    issue = db.query(Issue).filter(Issue.id == id_or_key).one_or_none()
    if issue is not None:
        return issue
    # Try by synthesized numeric id by scanning matches. Cheap because we
    # only do this when the lookup-by-key failed.
    if id_or_key.isdigit():
        from app.api.jira_compat.ids import numeric_id_for_issue
        for cand in db.query(Issue).all():
            if numeric_id_for_issue(cand.id) == id_or_key:
                return cand
    raise HTTPException(404, "Issue does not exist or you do not have permission to see it.")


# =====================================================================
# Issues
# =====================================================================


@router.get("/issue/{id_or_key}")
def get_issue(
    id_or_key: str,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    expand: Optional[str] = Query(None, description="Comma-separated list: renderedFields, changelog"),
    fields: Optional[str] = Query(None, description="(Accepted, currently ignored — full payload returned.)"),
) -> dict:
    issue = _resolve_issue_id_or_key(db, id_or_key)
    expansions = [e.strip() for e in (expand or "").split(",") if e.strip()]
    out = shapes.issue_to_jira(issue, db, base_url=_base_url(request), expand=expansions)
    # Populate isWatching now that we know the caller.
    out["fields"]["watches"]["isWatching"] = (
        db.query(Watcher).filter(Watcher.issue_id == issue.id, Watcher.user_id == user.id).count() > 0
    )
    return out


@router.post("/issue", status_code=201)
def create_issue(
    payload: dict[str, Any],
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> dict:
    """Create an issue from Jira's nested `{ fields: { project: {key}, issuetype: {name}, summary, ... } }` payload."""
    fields = payload.get("fields") or {}
    project = fields.get("project") or {}
    project_key = project.get("key")
    if not project_key:
        # Accept project id too.
        if pid := project.get("id"):
            p = (
                db.query(Project).all()
            )
            from app.api.jira_compat.ids import numeric_id_for_project
            for cand in p:
                if numeric_id_for_project(cand.key) == str(pid):
                    project_key = cand.key
                    break
    if not project_key:
        raise HTTPException(400, {"errors": {"project": "Project is required."}})

    issuetype = fields.get("issuetype") or {}
    issue_type = issuetype.get("name") or issuetype.get("id") or "Task"
    # Map well-known Atlassian issuetype ids back to names.
    issuetype_name_by_id = {"1": "Bug", "3": "Task", "5": "Subtask", "10001": "Story", "10000": "Epic"}
    if issue_type in issuetype_name_by_id:
        issue_type = issuetype_name_by_id[issue_type]

    summary = fields.get("summary")
    if not summary:
        raise HTTPException(400, {"errors": {"summary": "Summary is required."}})

    priority_block = fields.get("priority") or {}
    priority = priority_block.get("name") or "Medium"

    assignee_block = fields.get("assignee")
    assignee_id: Optional[str] = None
    if isinstance(assignee_block, dict):
        # accountId -> user id reverse lookup
        aid = assignee_block.get("accountId")
        if aid:
            for u in db.query(User).all():
                if account_id_for(u.id) == aid:
                    assignee_id = u.id
                    break

    desc = shapes.adf_to_plaintext(fields.get("description"))

    parent_block = fields.get("parent") or {}
    parent_id = parent_block.get("key") if isinstance(parent_block, dict) else None

    epic_link = fields.get("customfield_10014")  # well-known: Epic Link
    labels = fields.get("labels") or []
    story_points = fields.get("customfield_10016")

    issue = issue_svc.create_issue(
        db,
        user,
        issue_svc.CreateIssueInput(
            project_key=project_key,
            issue_type=issue_type,
            summary=summary,
            description=desc,
            priority=priority,
            owner=assignee_id,
            story_points=int(story_points) if isinstance(story_points, (int, float)) else None,
            labels=list(labels) if labels else None,
            parent_id=parent_id,
            epic_id=epic_link if isinstance(epic_link, str) else None,
        ),
    )
    db.commit()

    iid = shapes.numeric_id_for_issue(issue.id)
    base = _base_url(request)
    return {
        "id": iid,
        "key": issue.id,
        "self": f"{base}/rest/api/3/issue/{iid}",
    }


@router.put("/issue/{id_or_key}", status_code=204)
def edit_issue(
    id_or_key: str,
    payload: dict[str, Any],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    """Apply a Jira-shape `{fields: {...}}` patch. Field-name mapping:
        fields.summary           -> summary
        fields.description (ADF) -> description (plaintext)
        fields.priority.name     -> priority
        fields.duedate           -> due_date
        fields.assignee.accountId-> (assign endpoint instead; ignored here for now)
        fields.labels            -> replace label set
        fields.customfield_10016 -> story_points
        fields.parent.key        -> parent_id
        fields.customfield_10014 -> epic_id
    """
    issue = _resolve_issue_id_or_key(db, id_or_key)
    fields = payload.get("fields") or {}
    patch: dict[str, Any] = {}
    if "summary" in fields:
        patch["summary"] = fields["summary"]
    if "description" in fields:
        patch["description"] = shapes.adf_to_plaintext(fields["description"])
    if "priority" in fields:
        block = fields["priority"] or {}
        if isinstance(block, dict) and "name" in block:
            patch["priority"] = block["name"]
    if "duedate" in fields:
        patch["due_date"] = fields["duedate"]
    if "customfield_10016" in fields:
        patch["story_points"] = fields["customfield_10016"]
    if "parent" in fields:
        block = fields["parent"] or {}
        if isinstance(block, dict):
            patch["parent_id"] = block.get("key")
    if "customfield_10014" in fields:
        patch["epic_id"] = fields["customfield_10014"]

    if patch:
        issue_svc.update_issue(db, user, issue.id, patch)

    if "labels" in fields:
        new_labels = list(fields["labels"] or [])
        # Replace strategy: add any that are new, remove any that were dropped.
        current = {l for l in [lab.label_name for lab in issue.labels]}
        for l in set(new_labels) - current:
            issue_svc.add_label(db, user, issue.id, l)
        for l in current - set(new_labels):
            issue_svc.remove_label(db, user, issue.id, l)

    if "assignee" in fields:
        block = fields["assignee"]
        if block is None:
            issue_svc.assign_issue(db, user, issue.id, None)
        elif isinstance(block, dict):
            aid = block.get("accountId")
            if aid is None:
                issue_svc.assign_issue(db, user, issue.id, None)
            else:
                target_id: Optional[str] = None
                for u in db.query(User).all():
                    if account_id_for(u.id) == aid:
                        target_id = u.id
                        break
                if target_id is None:
                    raise HTTPException(404, "Assignee not found.")
                issue_svc.assign_issue(db, user, issue.id, target_id)

    db.commit()


@router.delete("/issue/{id_or_key}", status_code=204)
def delete_issue(id_or_key: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_session)]):
    # Real Jira allows delete with the right permission. We don't expose
    # deletion in the legacy API and don't want to surprise an agent here.
    raise HTTPException(
        status.HTTP_405_METHOD_NOT_ALLOWED,
        "Issue deletion is not supported in this environment. Use a transition to 'Closed' / 'Won't Do' instead.",
    )


@router.put("/issue/{id_or_key}/assignee", status_code=204)
def set_assignee(
    id_or_key: str,
    payload: dict[str, Any],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    """PUT /rest/api/3/issue/{idOrKey}/assignee  body: {accountId: "..."} | {accountId: null}"""
    issue = _resolve_issue_id_or_key(db, id_or_key)
    aid = payload.get("accountId")
    target: Optional[str] = None
    if aid is not None:
        for u in db.query(User).all():
            if account_id_for(u.id) == aid:
                target = u.id
                break
        if target is None:
            raise HTTPException(404, "User does not exist.")
    issue_svc.assign_issue(db, user, issue.id, target)
    db.commit()


@router.get("/issue/{id_or_key}/transitions")
def list_transitions(
    id_or_key: str,
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> dict:
    from app.services import workflows
    issue = _resolve_issue_id_or_key(db, id_or_key)
    allowed = workflows.allowed_transitions_for_issue(db, issue)
    base = _base_url(request)
    transitions = []
    for t in allowed:
        # Build the target status reference.
        target_status = db.query(WorkflowStatus).filter(WorkflowStatus.id == t.to_status_id).one()
        transitions.append({
            "id": shapes.numeric_id_for_status(t.to_status_id),
            "name": t.name,
            "to": shapes.status_ref(target_status, base_url=base),
            "hasScreen": False,
            "isGlobal": False,
            "isInitial": False,
            "isAvailable": True,
            "isConditional": False,
        })
    return {"expand": "transitions", "transitions": transitions}


@router.post("/issue/{id_or_key}/transitions", status_code=204)
def do_transition(
    id_or_key: str,
    payload: dict[str, Any],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    """POST body shape:
        {
          "transition": {"id": "<status_id>"} | {"name": "<transition name>"},
          "update": {"comment": [{"add": {"body": "..."}}]} (optional)
        }
    We accept either the target status id OR a transition name (Jira's API
    accepts only id; we accept both because internal MCP tools pass names)."""
    from app.services import workflows
    issue = _resolve_issue_id_or_key(db, id_or_key)

    transition_block = payload.get("transition") or {}
    target = transition_block.get("id") or transition_block.get("name")
    if not target:
        raise HTTPException(400, {"errors": {"transition": "Transition id or name is required."}})

    # If `target` is a numeric id we synthesized, reverse-lookup the status name.
    status_name = target
    if isinstance(target, str) and target.isdigit():
        for s in db.query(WorkflowStatus).all():
            if shapes.numeric_id_for_status(s.id) == target:
                status_name = s.name
                break

    comment_body: Optional[str] = None
    update = payload.get("update") or {}
    if "comment" in update:
        for op in update["comment"]:
            if "add" in op:
                body = op["add"].get("body")
                comment_body = shapes.adf_to_plaintext(body) if not isinstance(body, str) else body
                break

    issue_svc.transition_issue(db, user, issue.id, status_name, comment_body)
    db.commit()


# ----- Comments -------------------------------------------------------------


@router.get("/issue/{id_or_key}/comment")
def list_comments(
    id_or_key: str,
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    startAt: int = 0,
    maxResults: int = 50,
) -> dict:
    issue = _resolve_issue_id_or_key(db, id_or_key)
    comments = (
        db.query(Comment).filter(Comment.issue_id == issue.id)
        .order_by(Comment.created_at).all()
    )
    total = len(comments)
    sliced = comments[startAt:startAt + maxResults]
    base = _base_url(request)
    return {
        "startAt": startAt,
        "maxResults": maxResults,
        "total": total,
        "comments": [shapes.comment_ref(c, db, base_url=base) for c in sliced],
    }


@router.post("/issue/{id_or_key}/comment", status_code=201)
def add_comment(
    id_or_key: str,
    payload: dict[str, Any],
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> dict:
    issue = _resolve_issue_id_or_key(db, id_or_key)
    body = payload.get("body")
    text = shapes.adf_to_plaintext(body) if not isinstance(body, str) else body
    if not text:
        raise HTTPException(400, {"errors": {"body": "Comment body is required."}})
    c = issue_svc.add_comment(db, user, issue.id, text)
    db.commit()
    return shapes.comment_ref(c, db, base_url=_base_url(request))


@router.put("/issue/{id_or_key}/comment/{comment_id}")
def update_comment_endpoint(
    id_or_key: str,
    comment_id: str,
    payload: dict[str, Any],
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> dict:
    issue = _resolve_issue_id_or_key(db, id_or_key)
    # Map synthetic numeric id -> internal id.
    target: Optional[Comment] = None
    for c in db.query(Comment).filter(Comment.issue_id == issue.id).all():
        if c.id == comment_id or shapes.numeric_id_for_comment(c.id) == comment_id:
            target = c
            break
    if target is None:
        raise HTTPException(404, "Comment does not exist or you do not have permission to see it.")
    body = payload.get("body")
    text = shapes.adf_to_plaintext(body) if not isinstance(body, str) else body
    if not text:
        raise HTTPException(400, {"errors": {"body": "Comment body is required."}})
    updated = issue_svc.update_comment(db, user, issue.id, target.id, text)
    db.commit()
    return shapes.comment_ref(updated, db, base_url=_base_url(request))


@router.delete("/issue/{id_or_key}/comment/{comment_id}", status_code=204)
def delete_comment_endpoint(
    id_or_key: str,
    comment_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    issue = _resolve_issue_id_or_key(db, id_or_key)
    target: Optional[Comment] = None
    for c in db.query(Comment).filter(Comment.issue_id == issue.id).all():
        if c.id == comment_id or shapes.numeric_id_for_comment(c.id) == comment_id:
            target = c
            break
    if target is None:
        raise HTTPException(404, "Comment does not exist or you do not have permission to see it.")
    issue_svc.delete_comment(db, user, issue.id, target.id)
    db.commit()


# ----- Watchers -------------------------------------------------------------


@router.get("/issue/{id_or_key}/watchers")
def list_watchers(
    id_or_key: str,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> dict:
    issue = _resolve_issue_id_or_key(db, id_or_key)
    base = _base_url(request)
    watcher_users = (
        db.query(User)
        .join(Watcher, Watcher.user_id == User.id)
        .filter(Watcher.issue_id == issue.id)
        .all()
    )
    iid = shapes.numeric_id_for_issue(issue.id)
    return {
        "self": f"{base}/rest/api/3/issue/{iid}/watchers",
        "isWatching": any(w.id == user.id for w in watcher_users),
        "watchCount": len(watcher_users),
        "watchers": [shapes.user_ref(u, base_url=base) for u in watcher_users],
    }


@router.post("/issue/{id_or_key}/watchers", status_code=204)
async def add_watcher(
    id_or_key: str,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    """POST body is a JSON string `"accountId"`. Real Jira accepts an
    empty/missing body meaning the caller watches themselves."""
    issue = _resolve_issue_id_or_key(db, id_or_key)
    raw = await request.body()
    aid: Optional[str] = None
    if raw:
        try:
            import json
            parsed = json.loads(raw)
            if isinstance(parsed, str) and parsed:
                aid = parsed
        except Exception:
            pass
    target_user = user
    if aid:
        for u in db.query(User).all():
            if account_id_for(u.id) == aid:
                target_user = u
                break
    issue_svc.watch_issue(db, target_user, issue.id)
    db.commit()


@router.delete("/issue/{id_or_key}/watchers", status_code=204)
def remove_watcher(
    id_or_key: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    accountId: Optional[str] = None,
):
    issue = _resolve_issue_id_or_key(db, id_or_key)
    target_user = user
    if accountId:
        for u in db.query(User).all():
            if account_id_for(u.id) == accountId:
                target_user = u
                break
    issue_svc.unwatch_issue(db, target_user, issue.id)
    db.commit()


# ----- Changelog ------------------------------------------------------------


@router.get("/issue/{id_or_key}/changelog")
def changelog(
    id_or_key: str,
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    startAt: int = 0,
    maxResults: int = 100,
) -> dict:
    issue = _resolve_issue_id_or_key(db, id_or_key)
    block = shapes._changelog_for(issue, db, base_url=_base_url(request))
    histories = block["histories"]
    sliced = histories[startAt:startAt + maxResults]
    return {
        "self": f"{_base_url(request)}/rest/api/3/issue/{shapes.numeric_id_for_issue(issue.id)}/changelog",
        "nextPage": None,
        "maxResults": maxResults,
        "startAt": startAt,
        "total": len(histories),
        "isLast": startAt + len(sliced) >= len(histories),
        "values": sliced,
    }


# =====================================================================
# Issue Links
# =====================================================================


@router.post("/issueLink", status_code=201)
def add_issue_link(
    payload: dict[str, Any],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    """Body: {type: {name}, inwardIssue: {key}, outwardIssue: {key}}.
    Jira's semantics: `outwardIssue` is the source of the named relation.
    e.g. `A blocks B` -> outwardIssue=A, inwardIssue=B, type.name='Blocks'."""
    type_block = payload.get("type") or {}
    outward = (payload.get("outwardIssue") or {}).get("key")
    inward = (payload.get("inwardIssue") or {}).get("key")
    if not outward or not inward:
        raise HTTPException(400, {"errors": {"issuelink": "outwardIssue.key and inwardIssue.key are required."}})

    # Reverse-map type name to our internal link_type code.
    type_name = (type_block.get("name") or "").lower()
    reverse = {info[0].lower(): k for k, info in shapes._LINK_TYPE_INFO.items()}
    link_type = reverse.get(type_name, type_name or "relates")
    issue_svc.link_issues(db, user, outward, inward, link_type)
    db.commit()


@router.delete("/issueLink/{link_id}", status_code=204)
def remove_issue_link(
    link_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
):
    for l in db.query(IssueLink).all():
        if l.id == link_id or numeric_id_for_link(l.id) == link_id:
            issue_svc.unlink_issues(db, user, l.source_id, l.target_id, l.link_type)
            db.commit()
            return
    raise HTTPException(404, "Issue link does not exist or you do not have permission to see it.")


@router.get("/issueLinkType")
def list_link_types(
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
) -> dict:
    base = _base_url(request)
    return {
        "issueLinkTypes": [
            shapes._link_type(k, base_url=base) for k in shapes._LINK_TYPE_INFO
        ],
    }


# =====================================================================
# Search
# =====================================================================


def _search_response(
    db: Session,
    request: Request,
    jql: str,
    start_at: int,
    max_results: int,
    fields: Optional[list[str]] = None,
    user: Optional[User] = None,
) -> dict:
    rows, total = search(db, jql, current_user=user, limit=max_results, offset=start_at)
    base = _base_url(request)
    issues = [shapes.issue_to_jira(i, db, base_url=base) for i in rows]
    # Real Jira's `fields` param filters which fields are returned. Implement
    # the common cases (*all, *navigable, comma list, exclusion with -).
    if fields:
        wanted: set[str] = set()
        exclude: set[str] = set()
        star_all = False
        for f in fields:
            f = f.strip()
            if not f:
                continue
            if f == "*all":
                star_all = True
            elif f.startswith("-"):
                exclude.add(f[1:])
            else:
                wanted.add(f)
        for issue in issues:
            if not star_all and wanted:
                issue["fields"] = {k: v for k, v in issue["fields"].items() if k in wanted}
            for ex in exclude:
                issue["fields"].pop(ex, None)
    return {
        "expand": "schema,names",
        "startAt": start_at,
        "maxResults": max_results,
        "total": total,
        "isLast": start_at + len(issues) >= total,
        "issues": issues,
    }


@router.get("/search")
def search_jql(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    jql: str = Query("", description="JQL query."),
    startAt: int = 0,
    maxResults: int = 50,
    fields: Optional[str] = Query(None),
) -> dict:
    field_list = [f.strip() for f in (fields or "").split(",")] if fields else None
    return _search_response(db, request, jql or "", startAt, maxResults, field_list, user)


@router.post("/search")
def search_jql_post(
    payload: dict[str, Any],
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> dict:
    jql = payload.get("jql") or ""
    start_at = int(payload.get("startAt", 0))
    max_results = int(payload.get("maxResults", 50))
    fields = payload.get("fields")
    if isinstance(fields, str):
        fields = [f.strip() for f in fields.split(",") if f.strip()]
    return _search_response(db, request, jql, start_at, max_results, fields, user)


# =====================================================================
# Projects
# =====================================================================


@router.get("/project")
def list_projects(
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    base = _base_url(request)
    return [shapes.project_ref(p, base_url=base) for p in project_svc.list_projects(db)]


@router.get("/project/{key}")
def get_project(
    key: str,
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> dict:
    project = project_svc.get_project(db, key)
    base = _base_url(request)
    ref = shapes.project_ref(project, base_url=base)
    # Expand to a fuller representation matching real Jira's GET /project/{key}.
    lead = db.query(User).filter(User.id == project.lead_id).one_or_none() if project.lead_id else None
    return {
        **ref,
        "description": project.description or "",
        "lead": shapes.user_ref(lead, base_url=base) if lead else None,
        "issueTypes": [
            shapes.issuetype_ref(t, base_url=base)
            for t in ["Story", "Task", "Bug", "Epic", "Subtask"]
        ],
        "components": [],
        "versions": [],
        "roles": {},
        "style": "next-gen",
        "isPrivate": False,
        "properties": {},
    }


@router.get("/project/{key}/statuses")
def project_statuses(
    key: str,
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    project = project_svc.get_project(db, key)
    base = _base_url(request)
    statuses_by_issuetype = []
    statuses = (
        db.query(WorkflowStatus)
        .filter(WorkflowStatus.workflow_id == project.workflow_id)
        .order_by(WorkflowStatus.position)
        .all()
    )
    status_refs = [shapes.status_ref(s, base_url=base) for s in statuses]
    for issue_type in ["Story", "Task", "Bug", "Epic", "Subtask"]:
        statuses_by_issuetype.append({
            "self": f"{base}/rest/api/3/issuetype/{shapes.numeric_id_for_issuetype(issue_type)}",
            "id": shapes.numeric_id_for_issuetype(issue_type),
            "name": issue_type,
            "subtask": issue_type == "Subtask",
            "statuses": status_refs,
        })
    return statuses_by_issuetype


# =====================================================================
# Users + myself
# =====================================================================


@router.get("/myself")
def myself(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    return shapes.user_ref(user, base_url=_base_url(request))


@router.get("/user")
def get_user(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    accountId: Optional[str] = None,
    username: Optional[str] = None,
) -> dict:
    if not accountId and not username:
        raise HTTPException(400, {"errors": {"accountId": "accountId or username is required."}})
    target: Optional[User] = None
    if accountId:
        for u in db.query(User).all():
            if account_id_for(u.id) == accountId:
                target = u
                break
    elif username:
        target = db.query(User).filter(User.id == username).one_or_none()
    if target is None:
        raise HTTPException(404, "User does not exist.")
    return shapes.user_ref(target, base_url=_base_url(request))


@router.get("/user/search")
def search_users(
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    query: str = "",
    startAt: int = 0,
    maxResults: int = 50,
) -> list[dict]:
    q = (query or "").lower()
    base = _base_url(request)
    rows = []
    for u in db.query(User).order_by(User.name).all():
        if q and q not in u.name.lower() and q not in u.email.lower() and q not in (u.display_name or "").lower():
            continue
        rows.append(shapes.user_ref(u, base_url=base))
    return rows[startAt:startAt + maxResults]


# =====================================================================
# Metadata
# =====================================================================


@router.get("/priority")
def list_priorities(
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    base = _base_url(request)
    # Order Highest -> Lowest, matching Jira's display order.
    return [
        shapes.priority_ref(p, base_url=base)
        for p in ("Highest", "High", "Medium", "Low", "Lowest")
    ]


@router.get("/status")
def list_statuses(
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    base = _base_url(request)
    return [
        shapes.status_ref(s, base_url=base)
        for s in db.query(WorkflowStatus).order_by(WorkflowStatus.position).all()
    ]


@router.get("/issuetype")
def list_issuetypes(
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    base = _base_url(request)
    return [
        shapes.issuetype_ref(t, base_url=base)
        for t in ("Story", "Task", "Bug", "Epic", "Subtask")
    ]


@router.get("/serverInfo")
def server_info(request: Request) -> dict:
    """Real Jira returns build info here. Agents sometimes use this to detect
    the platform; we identify ourselves clearly while keeping field names."""
    return {
        "baseUrl": _base_url(request),
        "version": "1001.0.0-jirassic-park",
        "versionNumbers": [1001, 0, 0],
        "deploymentType": "Cloud",
        "buildNumber": 100001,
        "buildDate": "2026-05-27T00:00:00.000-0700",
        "serverTime": shapes.to_jira_datetime(_now_dt()),
        "scmInfo": "jirassic-park",
        "serverTitle": "Jirassic Park",
    }


@router.get("/field")
def list_fields(
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    """Compact `GET /rest/api/3/field` — enumerates the fields our issues
    have. Agents use this to know which `customfield_*` keys to read."""
    base = _base_url(request)
    return [
        {"id": "summary", "name": "Summary", "custom": False, "schema": {"type": "string"}},
        {"id": "issuetype", "name": "Issue Type", "custom": False, "schema": {"type": "issuetype"}},
        {"id": "status", "name": "Status", "custom": False, "schema": {"type": "status"}},
        {"id": "assignee", "name": "Assignee", "custom": False, "schema": {"type": "user"}},
        {"id": "reporter", "name": "Reporter", "custom": False, "schema": {"type": "user"}},
        {"id": "priority", "name": "Priority", "custom": False, "schema": {"type": "priority"}},
        {"id": "labels", "name": "Labels", "custom": False, "schema": {"type": "array", "items": "string"}},
        {"id": "description", "name": "Description", "custom": False, "schema": {"type": "string"}},
        {"id": "duedate", "name": "Due date", "custom": False, "schema": {"type": "date"}},
        {"id": "parent", "name": "Parent", "custom": False, "schema": {"type": "issue"}},
        {"id": "issuelinks", "name": "Linked Issues", "custom": False, "schema": {"type": "array", "items": "issuelink"}},
        {"id": "subtasks", "name": "Sub-tasks", "custom": False, "schema": {"type": "array", "items": "issue"}},
        {"id": "comment", "name": "Comment", "custom": False, "schema": {"type": "comments-page"}},
        {"id": "customfield_10016", "name": "Story Points", "custom": True, "schema": {"type": "number"}, "untranslatedName": "Story Points"},
        {"id": "customfield_10020", "name": "Sprint", "custom": True, "schema": {"type": "array", "items": "json"}, "untranslatedName": "Sprint"},
        {"id": "customfield_10014", "name": "Epic Link", "custom": True, "schema": {"type": "any"}, "untranslatedName": "Epic Link"},
        {"id": "customfield_10019", "name": "Flagged", "custom": True, "schema": {"type": "array", "items": "option"}, "untranslatedName": "Flagged"},
    ]


def _now_dt():
    from app.clock import now
    return now()
