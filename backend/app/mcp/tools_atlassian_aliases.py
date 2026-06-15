"""Atlassian-naming MCP tool aliases.

These mirror the tool names exposed by Atlassian's official MCP server. An
agent trained to call (e.g.) `getJiraIssue(issueIdOrKey="PLAT-60")` against
real Atlassian Cloud can call the exact same tool here.

Every alias is a thin wrapper around the canonical jira_* implementation in
tools_impl.py so:
- there's one source of truth for behavior (no drift)
- they share auth, error shapes, and audit semantics
- naming convergence is purely at the wire-format layer

We additionally translate the camelCase / accountId-flavored arguments into
our native id-based forms.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException
from mcp.server.fastmcp import Context

from app.api._helpers import issue_to_detail, issue_to_out
from app.api.jira_compat import shapes
from app.api.jira_compat.ids import account_id_for
from app.auth import resolve_user_by_token
from app.db import session_scope
from app.models import User
from app.services import issues as issue_svc
from app.services.search import search


def _resolve(db, auth_token: Optional[str], ctx: Optional[Context], *, required: bool = True) -> Optional[User]:
    """Same shape as tools_impl._resolve, duplicated here to avoid a circular import."""
    token = auth_token
    if token is None and ctx is not None:
        try:
            req = ctx.request_context.request  # type: ignore[union-attr]
            if req is not None:
                auth_header = req.headers.get("authorization") if hasattr(req, "headers") else None
                if auth_header:
                    parts = auth_header.split(None, 1)
                    if len(parts) == 2 and parts[0].lower() == "bearer":
                        token = parts[1].strip()
        except (AttributeError, ValueError):
            pass
    user = resolve_user_by_token(db, token)
    if required and user is None:
        raise HTTPException(401, "auth_token is required (or set Authorization: Bearer header).")
    return user


def _account_to_user_id(db, account_id: Optional[str]) -> Optional[str]:
    if not account_id:
        return None
    for u in db.query(User).all():
        if account_id_for(u.id) == account_id:
            return u.id
    raise HTTPException(404, f"No user with accountId='{account_id}'.")


def register(mcp) -> None:
    """Register Atlassian-named tool aliases on the MCP instance."""

    @mcp.tool(
        name="getJiraIssue",
        description=(
            "Get a Jira issue by key or id (e.g. 'PLAT-60' or '10234'). "
            "Returns the issue in Atlassian REST v3 shape: { id, key, self, "
            "fields: { summary, issuetype, status, assignee, ... } }. "
            "Alias for jira_get_issue with Jira-shape response."
        ),
    )
    def get_jira_issue(
        issueIdOrKey: str,
        expand: Optional[str] = None,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            issue = issue_svc.get_issue(db, issueIdOrKey)
            return shapes.issue_to_jira(
                issue, db,
                base_url="http://localhost",
                expand=[e.strip() for e in (expand or "").split(",") if e.strip()],
            )

    @mcp.tool(
        name="createJiraIssue",
        description=(
            "Create a Jira issue. Pass a Jira-shape payload: "
            "{ fields: { project: {key}, issuetype: {name}, summary, description, "
            "priority: {name}, assignee: {accountId}, labels, ... } }. "
            "Returns { id, key, self }. Alias for jira_create_issue."
        ),
    )
    def create_jira_issue(
        fields: dict[str, Any],
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            project = fields.get("project") or {}
            project_key = project.get("key")
            if not project_key:
                raise HTTPException(400, "fields.project.key is required.")
            issuetype = fields.get("issuetype") or {}
            issue_type = issuetype.get("name") or "Task"
            priority_block = fields.get("priority") or {}
            priority = priority_block.get("name") or "Medium"
            assignee_block = fields.get("assignee") or {}
            assignee_id = _account_to_user_id(db, assignee_block.get("accountId")) if isinstance(assignee_block, dict) else None
            desc_input = fields.get("description")
            desc = shapes.adf_to_plaintext(desc_input) if not isinstance(desc_input, str) else desc_input
            parent = (fields.get("parent") or {}).get("key")
            epic_link = fields.get("customfield_10014")
            story_points = fields.get("customfield_10016")
            labels = fields.get("labels") or []
            summary = fields.get("summary")
            if not summary:
                raise HTTPException(400, "fields.summary is required.")
            issue = issue_svc.create_issue(
                db, user,
                issue_svc.CreateIssueInput(
                    project_key=project_key,
                    issue_type=issue_type,
                    summary=summary,
                    description=desc,
                    priority=priority,
                    owner=assignee_id,
                    story_points=int(story_points) if isinstance(story_points, (int, float)) else None,
                    labels=list(labels) if labels else None,
                    parent_id=parent,
                    epic_id=epic_link if isinstance(epic_link, str) else None,
                ),
            )
            iid = shapes.numeric_id_for_issue(issue.id)
            return {"id": iid, "key": issue.id, "self": f"http://localhost/rest/api/3/issue/{iid}"}

    @mcp.tool(
        name="editJiraIssue",
        description=(
            "Edit a Jira issue's fields. Pass `issueIdOrKey` and a `fields` "
            "block in Jira shape. Editable: summary, description (ADF or "
            "string), priority.name, duedate, labels, parent.key, "
            "customfield_10016 (story points), customfield_10014 (epic link), "
            "assignee.accountId. Returns { key }."
        ),
    )
    def edit_jira_issue(
        issueIdOrKey: str,
        fields: dict[str, Any],
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            issue = issue_svc.get_issue(db, issueIdOrKey)
            patch: dict[str, Any] = {}
            if "summary" in fields:
                patch["summary"] = fields["summary"]
            if "description" in fields:
                v = fields["description"]
                patch["description"] = shapes.adf_to_plaintext(v) if not isinstance(v, str) else v
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
                current = {lab.label_name for lab in issue.labels}
                for l in set(new_labels) - current:
                    issue_svc.add_label(db, user, issue.id, l)
                for l in current - set(new_labels):
                    issue_svc.remove_label(db, user, issue.id, l)
            if "assignee" in fields:
                block = fields["assignee"]
                if block is None or block.get("accountId") is None:
                    issue_svc.assign_issue(db, user, issue.id, None)
                else:
                    target = _account_to_user_id(db, block["accountId"])
                    issue_svc.assign_issue(db, user, issue.id, target)
            return {"key": issue.id}

    @mcp.tool(
        name="getJiraIssueTransitions",
        description=(
            "List the legal next-status transitions for an issue. "
            "Returns { transitions: [{id, name, to: {id, name, ...}}, ...] }. "
            "Use this BEFORE transitionJiraIssue to discover the exact target name strings."
        ),
    )
    def get_jira_issue_transitions(
        issueIdOrKey: str,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        from app.services import workflows
        from app.models import WorkflowStatus
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            issue = issue_svc.get_issue(db, issueIdOrKey)
            allowed = workflows.allowed_transitions_for_issue(db, issue)
            transitions = []
            for t in allowed:
                target_status = db.query(WorkflowStatus).filter(WorkflowStatus.id == t.to_status_id).one()
                transitions.append({
                    "id": shapes.numeric_id_for_status(t.to_status_id),
                    "name": t.name,
                    "to": shapes.status_ref(target_status, base_url="http://localhost"),
                    "hasScreen": False,
                    "isGlobal": False,
                    "isInitial": False,
                    "isAvailable": True,
                    "isConditional": False,
                })
            return {"expand": "transitions", "transitions": transitions}

    @mcp.tool(
        name="transitionJiraIssue",
        description=(
            "Transition a Jira issue to a new status. Pass `transition.id` (from "
            "getJiraIssueTransitions) OR `transition.name` (e.g. 'Submit for review'). "
            "Optionally include `update.comment` to add a comment with the transition. "
            "Errors list the allowed transitions if the requested one is illegal."
        ),
    )
    def transition_jira_issue(
        issueIdOrKey: str,
        transition: dict[str, Any],
        update: Optional[dict[str, Any]] = None,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        from app.models import WorkflowStatus
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            issue = issue_svc.get_issue(db, issueIdOrKey)
            target = (transition or {}).get("id") or (transition or {}).get("name")
            if not target:
                raise HTTPException(400, "transition.id or transition.name is required.")
            if isinstance(target, str) and target.isdigit():
                for s in db.query(WorkflowStatus).all():
                    if shapes.numeric_id_for_status(s.id) == target:
                        target = s.name
                        break
            comment_body: Optional[str] = None
            if update and "comment" in update:
                for op in update["comment"]:
                    if "add" in op:
                        b = op["add"].get("body")
                        comment_body = shapes.adf_to_plaintext(b) if not isinstance(b, str) else b
                        break
            issue_svc.transition_issue(db, user, issue.id, target, comment_body)
            return {"key": issue.id}

    @mcp.tool(
        name="assignJiraIssue",
        description=(
            "Assign a Jira issue. Pass `accountId` (from getJiraUser) or null to "
            "unassign. Alias for jira_assign_issue."
        ),
    )
    def assign_jira_issue(
        issueIdOrKey: str,
        accountId: Optional[str],
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            target = _account_to_user_id(db, accountId) if accountId else None
            issue = issue_svc.assign_issue(db, user, issueIdOrKey, target)
            return {"key": issue.id, "accountId": accountId}

    @mcp.tool(
        name="addJiraIssueComment",
        description=(
            "Add a comment to a Jira issue. `body` is a plaintext string or "
            "ADF document. Returns the created comment in Jira shape."
        ),
    )
    def add_jira_issue_comment(
        issueIdOrKey: str,
        body: Any,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            text = body if isinstance(body, str) else shapes.adf_to_plaintext(body)
            if not text:
                raise HTTPException(400, "body is required.")
            c = issue_svc.add_comment(db, user, issueIdOrKey, text)
            return shapes.comment_ref(c, db, base_url="http://localhost")

    @mcp.tool(
        name="getJiraIssueComments",
        description="List comments on a Jira issue in Jira shape.",
    )
    def get_jira_issue_comments(
        issueIdOrKey: str,
        startAt: int = 0,
        maxResults: int = 50,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        from app.models import Comment
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            issue = issue_svc.get_issue(db, issueIdOrKey)
            comments = db.query(Comment).filter(Comment.issue_id == issue.id).order_by(Comment.created_at).all()
            sliced = comments[startAt:startAt + maxResults]
            return {
                "startAt": startAt, "maxResults": maxResults, "total": len(comments),
                "comments": [shapes.comment_ref(c, db, base_url="http://localhost") for c in sliced],
            }

    @mcp.tool(
        name="searchJiraIssuesUsingJql",
        description=(
            "Search Jira issues with JQL. Returns issues in Jira shape with "
            "startAt/maxResults/total pagination. Alias for jira_search with "
            "Jira-shape response."
        ),
    )
    def search_jira_issues_using_jql(
        jql: str,
        startAt: int = 0,
        maxResults: int = 50,
        fields: Optional[list[str]] = None,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            rows, total = search(db, jql, current_user=user, limit=maxResults, offset=startAt)
            issues = [shapes.issue_to_jira(i, db, base_url="http://localhost") for i in rows]
            if fields:
                wanted = {f for f in fields if not f.startswith("-") and f != "*all"}
                exclude = {f[1:] for f in fields if f.startswith("-")}
                star = "*all" in fields
                for issue in issues:
                    if not star and wanted:
                        issue["fields"] = {k: v for k, v in issue["fields"].items() if k in wanted}
                    for ex in exclude:
                        issue["fields"].pop(ex, None)
            return {
                "expand": "schema,names",
                "startAt": startAt,
                "maxResults": maxResults,
                "total": total,
                "isLast": startAt + len(issues) >= total,
                "issues": issues,
            }

    @mcp.tool(
        name="getJiraMyself",
        description="Get the current authenticated user in Atlassian shape (accountId, displayName, ...).",
    )
    def get_jira_myself(auth_token: Optional[str] = None, ctx: Context = None) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            return shapes.user_ref(user, base_url="http://localhost")

    @mcp.tool(
        name="getJiraUser",
        description="Get a Jira user by accountId or username (Jirassic Park user id).",
    )
    def get_jira_user(
        accountId: Optional[str] = None,
        username: Optional[str] = None,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
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
            return shapes.user_ref(target, base_url="http://localhost")

    @mcp.tool(
        name="searchJiraUsers",
        description="Find users by query (matches name/email/displayName).",
    )
    def search_jira_users(
        query: str = "",
        startAt: int = 0,
        maxResults: int = 50,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> list[dict]:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            q = (query or "").lower()
            rows: list[dict] = []
            for u in db.query(User).order_by(User.name).all():
                if q and q not in u.name.lower() and q not in u.email.lower() and q not in (u.display_name or "").lower():
                    continue
                rows.append(shapes.user_ref(u, base_url="http://localhost"))
            return rows[startAt:startAt + maxResults]

    @mcp.tool(
        name="getJiraProject",
        description="Get a Jira project by key in Atlassian shape.",
    )
    def get_jira_project(
        projectIdOrKey: str,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        from app.services import projects as project_svc
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            project = project_svc.get_project(db, projectIdOrKey)
            base = "http://localhost"
            ref = shapes.project_ref(project, base_url=base)
            lead = db.query(User).filter(User.id == project.lead_id).one_or_none() if project.lead_id else None
            return {
                **ref,
                "description": project.description or "",
                "lead": shapes.user_ref(lead, base_url=base) if lead else None,
                "issueTypes": [shapes.issuetype_ref(t, base_url=base) for t in ("Story", "Task", "Bug", "Epic", "Subtask")],
                "components": [], "versions": [], "roles": {},
                "style": "next-gen", "isPrivate": False, "properties": {},
            }

    @mcp.tool(
        name="getJiraProjects",
        description="List all Jira projects in Atlassian shape.",
    )
    def get_jira_projects(
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> list[dict]:
        from app.services import projects as project_svc
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            return [shapes.project_ref(p, base_url="http://localhost") for p in project_svc.list_projects(db)]
