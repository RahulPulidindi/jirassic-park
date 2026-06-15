"""MCP tools. Each `jira_*` tool wraps the same service-layer function the REST
API uses, so REST and MCP produce identical state mutations.

Authentication: every tool accepts an optional `auth_token` argument. If not
provided, the tool falls back to the `Authorization` header on the incoming
HTTP request (if any). If neither is present, mutating tools raise.

Tool docstrings are descriptive on purpose - agents read them and need pitfalls
called out explicitly.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import HTTPException
from mcp.server.fastmcp import Context

from app.api._helpers import history_for_issue, issue_to_detail, issue_to_out
from app.auth import resolve_user_by_token
from app.db import session_scope
from app.models import (
    Issue,
    SavedFilter,
    Sprint,
    SprintIssue,
    User,
    WorkflowStatus,
)
from app.schemas.api import (
    ActivityOut,
    AdminResetOut,
    AllowedTransitionOut,
    CommentOut,
    IssueDetailOut,
    IssueLinkOut,
    IssueOut,
    ProjectOut,
    ProjectSummaryOut,
    SavedFilterOut,
    SprintOut,
    UserOut,
    WorkflowOut,
)
from app.services import (
    boards as board_svc,
    issues as issue_svc,
    projects as project_svc,
    sprints as sprint_svc,
)
from app.services.boards import snapshot_board
from app.services.search import search


# ---- Helpers --------------------------------------------------------------


def _token_from_ctx(ctx: Optional[Context]) -> Optional[str]:
    if ctx is None:
        return None
    try:
        req = ctx.request_context.request  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        return None
    if req is None:
        return None
    auth = req.headers.get("authorization") if hasattr(req, "headers") else None
    if not auth:
        return None
    parts = auth.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def _resolve(db, auth_token: Optional[str], ctx: Optional[Context], *, required: bool = True) -> Optional[User]:
    token = auth_token or _token_from_ctx(ctx)
    user = resolve_user_by_token(db, token)
    if required and user is None:
        raise HTTPException(401, "auth_token is required for this tool (or set Authorization: Bearer header).")
    return user


def _dump(obj) -> dict:
    """Convert a Pydantic model to a JSON-safe dict for the MCP response."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return obj


def _err(detail: str | HTTPException) -> dict:
    if isinstance(detail, HTTPException):
        return {"error": detail.detail, "status": detail.status_code}
    return {"error": str(detail)}


def _parse_iso(s: Optional[str]):
    """Parse an ISO-8601 string into a naive UTC datetime, or None if `s` is None.

    MCP tools take JSON-friendly primitives (no Pydantic on the call), so date/time
    arguments arrive as strings and we coerce them here.
    """
    if s is None:
        return None
    from datetime import datetime, timezone
    s = s.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as e:
        raise HTTPException(422, f"Invalid ISO timestamp '{s}': {e}") from None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# ---- Registration ---------------------------------------------------------


def register(mcp) -> None:
    """Register every jira_* tool on the FastMCP instance."""

    @mcp.tool(
        description=(
            "Return information about the currently-authenticated user. Useful to "
            "verify the agent's identity before doing anything that depends on `currentUser()`."
        )
    )
    def jira_whoami(auth_token: Optional[str] = None, ctx: Context = None) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            return _dump(UserOut.model_validate(user))

    @mcp.tool(
        description=(
            "List all projects. Returns project keys, names, descriptions, leads, and workflow ids. "
            "Use this first to see what projects exist before searching for issues."
        )
    )
    def jira_list_projects(auth_token: Optional[str] = None, ctx: Context = None) -> list[dict]:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            return [_dump(ProjectOut.model_validate(p)) for p in project_svc.list_projects(db)]

    @mcp.tool(
        description=(
            "Get a project's metadata (workflow_id, lead, type, color). Pass the project key, e.g. 'SCRUM'."
        )
    )
    def jira_get_project(key: str, auth_token: Optional[str] = None, ctx: Context = None) -> dict:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            return _dump(ProjectOut.model_validate(project_svc.get_project(db, key)))

    @mcp.tool(
        description=(
            "Create a new project. Admin role required. `key` must be unique and uppercase by convention "
            "(e.g. 'INFRA'). `workflow_id` selects the state machine; use `jira_get_workflow` on an "
            "existing project to discover valid workflow ids."
        )
    )
    def jira_create_project(
        key: str,
        name: str,
        workflow_id: str,
        description: Optional[str] = None,
        lead_id: Optional[str] = None,
        project_type: str = "software",
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            p = project_svc.create_project(
                db, user, key=key, name=name, description=description,
                workflow_id=workflow_id, lead_id=lead_id, project_type=project_type,
            )
            return _dump(ProjectOut.model_validate(p))

    @mcp.tool(
        description=(
            "Update project metadata. `patch` accepts a subset of: name, description, lead_id, "
            "default_assignee, avatar_color. Admin role required."
        )
    )
    def jira_update_project(
        key: str,
        patch: dict[str, Any],
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            p = project_svc.update_project(db, user, key, patch)
            return _dump(ProjectOut.model_validate(p))

    @mcp.tool(
        description=(
            "Get the full workflow for a project: list of statuses (with categories and colors) "
            "and the legal transitions between them. Use this BEFORE calling `jira_transition_issue` "
            "to discover what target statuses exist and what they're named — `jira_get_issue` only "
            "tells you which transitions are legal from the issue's current state."
        )
    )
    def jira_get_workflow(
        project_key: str,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            p = project_svc.get_project(db, project_key)
            return _dump(WorkflowOut.model_validate(p.workflow))

    @mcp.tool(
        description=(
            "One-call situational awareness: counts by status, priority, and assignee for a project, "
            "active sprint progress (todo/in_progress/done counts), and the 15 most-recent activities. "
            "Prefer this over multiple smaller calls when an agent first encounters a project."
        )
    )
    def jira_summarize_project(key: str, auth_token: Optional[str] = None, ctx: Context = None) -> dict:
        from app.api.projects import project_summary  # reuse exact same logic as REST

        # Build a fake request via direct call to the function
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            # Call the same handler implementation
            summary = _project_summary_inline(db, key)
            return _dump(summary)

    @mcp.tool(
        description=(
            "Get an issue's full detail by id (e.g. 'SCRUM-12'). Response includes:\n"
            "- summary, description, status, priority, assignee/reporter, labels, story_points, sprint\n"
            "- **allowed_transitions**: the only legal next statuses (use one of these with jira_transition_issue)\n"
            "- outbound_links, inbound_links, recent_comments\n"
            "Use this before calling jira_transition_issue or jira_assign_issue - "
            "you'll get the exact target-status name strings the API expects."
        )
    )
    def jira_get_issue(id: str, auth_token: Optional[str] = None, ctx: Context = None) -> dict:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            issue = issue_svc.get_issue(db, id)
            return _dump(issue_to_detail(db, issue))

    @mcp.tool(
        description=(
            "Search issues using JQL-lite. Supported features:\n"
            "- field comparisons: status = \"In Progress\", priority in (High, Highest), assignee = currentUser(), "
            "created >= -7d, labels = \"infra\", text ~ \"deploy\"\n"
            "- booleans: AND, OR, NOT, parentheses\n"
            "- ordering: ORDER BY priority DESC, created ASC\n"
            "- functions: currentUser(), unassigned(), now()\n"
            "- saved filter resolution: filter = \"My Open Bugs\"\n\n"
            "Returns up to `limit` issues plus the total match count. Pitfalls:\n"
            "- Status names are case-sensitive: use \"In Progress\" not \"in progress\"\n"
            "- `assignee` and `owner` are aliases; both work\n"
            "- Relative dates are negative offsets (-7d means 7 days ago)"
        )
    )
    def jira_search(
        jql: str,
        limit: int = 50,
        offset: int = 0,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            rows, total = search(db, jql, current_user=user, limit=limit, offset=offset)
            return {
                "jql": jql, "total": total, "limit": limit, "offset": offset,
                "issues": [_dump(issue_to_out(db, i)) for i in rows],
            }

    @mcp.tool(
        description=(
            "Create a new issue in the given project.\n"
            "- issue_type: Story | Task | Bug | Epic | Subtask (default Task)\n"
            "- priority: Lowest | Low | Medium | High | Highest (default Medium)\n"
            "- owner: user id (e.g. 'user_sarah_kim') or null for unassigned\n"
            "- parent_id: the parent issue id if this is a Subtask\n"
            "- epic_id: the Epic this issue belongs to (any non-Epic type)\n"
            "Returns the created issue with allowed_transitions populated."
        )
    )
    def jira_create_issue(
        project_key: str,
        summary: str,
        issue_type: str = "Task",
        description: Optional[str] = None,
        priority: str = "Medium",
        owner: Optional[str] = None,
        story_points: Optional[int] = None,
        labels: Optional[list[str]] = None,
        parent_id: Optional[str] = None,
        epic_id: Optional[str] = None,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            issue = issue_svc.create_issue(
                db, user, issue_svc.CreateIssueInput(
                    project_key=project_key, issue_type=issue_type, summary=summary,
                    description=description, priority=priority, owner=owner,
                    story_points=story_points, labels=labels,
                    parent_id=parent_id, epic_id=epic_id,
                ),
            )
            return _dump(issue_to_detail(db, issue))

    @mcp.tool(
        description=(
            "Update editable fields on an issue. `patch` accepts a subset of:\n"
            "summary, description, priority, story_points, due_date (YYYY-MM-DD), "
            "parent_id, epic_id, resolution.\n"
            "To change status use jira_transition_issue. To change assignee use jira_assign_issue."
        )
    )
    def jira_update_issue(
        id: str,
        patch: dict[str, Any],
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            issue = issue_svc.update_issue(db, user, id, patch)
            return _dump(issue_to_detail(db, issue))

    @mcp.tool(
        description=(
            "Transition an issue to a new status. `to_status` is the human-readable status NAME "
            "(e.g. 'In Progress', not the status_id). On failure (illegal transition, guard violation, "
            "or insufficient permissions) the error message lists the allowed next statuses. "
            "Optionally pass `comment` to leave a comment alongside the transition."
        )
    )
    def jira_transition_issue(
        id: str,
        to_status: str,
        comment: Optional[str] = None,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            issue = issue_svc.transition_issue(db, user, id, to_status, comment)
            return _dump(issue_to_detail(db, issue))

    @mcp.tool(
        description=(
            "Assign an issue to a user. Pass `assignee` = user id (e.g. 'user_sarah_kim'). "
            "Pass `assignee` = null to unassign. To find user ids use jira_list_users."
        )
    )
    def jira_assign_issue(
        id: str,
        assignee: Optional[str],
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            issue = issue_svc.assign_issue(db, user, id, assignee)
            return _dump(issue_to_detail(db, issue))

    @mcp.tool(
        description=(
            "Move an issue to a different sprint, or pull it back to the backlog. "
            "Pass `sprint_id` = sprint id (use jira_list_sprints to discover), or "
            "`sprint_id` = null to remove the issue from any sprint."
        )
    )
    def jira_set_sprint(
        id: str,
        sprint_id: Optional[str],
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            issue = issue_svc.set_sprint(db, user, id, sprint_id)
            return _dump(issue_to_detail(db, issue))

    @mcp.tool(
        description=(
            "Add a comment to an issue. Body is Markdown. Optionally pass `parent_comment_id` to "
            "reply in a thread. `@user_id` or `@first_last` mentions in the body deliver "
            "notifications to that user (visible via `jira_my_mentions`)."
        )
    )
    def jira_add_comment(
        id: str,
        body: str,
        parent_comment_id: Optional[str] = None,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            c = issue_svc.add_comment(db, user, id, body, parent_comment_id=parent_comment_id)
            return _dump(CommentOut.model_validate(c))

    @mcp.tool(
        description=(
            "Edit an existing comment. Only the original author or an admin can edit. "
            "Sets `edited_at`, re-parses `@mentions`, and emits one `mentioned` activity "
            "per *newly* tagged user (existing mentions are not re-notified)."
        )
    )
    def jira_update_comment(
        issue_id: str,
        comment_id: str,
        body: str,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            c = issue_svc.update_comment(db, user, issue_id, comment_id, body)
            return _dump(CommentOut.model_validate(c))

    @mcp.tool(
        description=(
            "Delete a comment. Only the original author or an admin can delete. "
            "The original body is preserved in a `comment_deleted` activity row so the "
            "audit log stays complete."
        )
    )
    def jira_delete_comment(
        issue_id: str,
        comment_id: str,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            issue_svc.delete_comment(db, user, issue_id, comment_id)
            return {"ok": True, "issue_id": issue_id, "comment_id": comment_id}

    @mcp.tool(
        description=(
            "Link two issues. link_type is one of: blocks, relates, duplicates, clones, causes. "
            "Direction is source -> target (e.g. 'A blocks B' means add link with source=A, target=B, type=blocks)."
        )
    )
    def jira_link_issues(
        source: str,
        target: str,
        link_type: str = "relates",
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            link = issue_svc.link_issues(db, user, source, target, link_type)
            return _dump(IssueLinkOut.model_validate(link))

    @mcp.tool(
        description=(
            "Remove an existing link between two issues. Inverse of `jira_link_issues`. "
            "Idempotent — missing link is a no-op. Emits an `unlinked` activity."
        )
    )
    def jira_unlink_issues(
        source: str,
        target: str,
        link_type: str = "relates",
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            issue_svc.unlink_issues(db, user, source, target, link_type)
            return {"ok": True, "source": source, "target": target, "link_type": link_type}

    @mcp.tool(
        description="Add a label to an issue. The label is created on the fly if it doesn't exist."
    )
    def jira_add_label(
        id: str, label: str, auth_token: Optional[str] = None, ctx: Context = None
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            issue = issue_svc.add_label(db, user, id, label)
            return _dump(issue_to_detail(db, issue))

    @mcp.tool(description="Remove a label from an issue. Idempotent.")
    def jira_remove_label(
        id: str, label: str, auth_token: Optional[str] = None, ctx: Context = None
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            issue = issue_svc.remove_label(db, user, id, label)
            return _dump(issue_to_detail(db, issue))

    @mcp.tool(description="Watch an issue (subscribe to updates).")
    def jira_watch_issue(
        id: str, auth_token: Optional[str] = None, ctx: Context = None
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            issue = issue_svc.watch_issue(db, user, id)
            return _dump(issue_to_detail(db, issue))

    @mcp.tool(description="Unwatch an issue (unsubscribe). Idempotent.")
    def jira_unwatch_issue(
        id: str, auth_token: Optional[str] = None, ctx: Context = None
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            issue = issue_svc.unwatch_issue(db, user, id)
            return _dump(issue_to_detail(db, issue))

    @mcp.tool(
        description=(
            "List all comments on an issue in chronological order. Pairs with `jira_add_comment`. "
            "Returns each comment's body, author, parent (for threads), mentions, and timestamps."
        )
    )
    def jira_list_comments(
        id: str, auth_token: Optional[str] = None, ctx: Context = None
    ) -> list[dict]:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            return [_dump(CommentOut.model_validate(c)) for c in issue_svc.list_comments(db, id)]

    @mcp.tool(
        description=(
            "Bulk-transition every issue matching a JQL query to the given status. Each transition "
            "is run through the regular state machine and audit log; transitions that fail (illegal "
            "from current status, guard violation, missing permission) are reported in `failed[]`. "
            "Useful for sprint triage. Pass `comment` to add the same comment to each issue."
        )
    )
    def jira_bulk_transition(
        jql: str,
        to_status: str,
        comment: Optional[str] = None,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            rows, total = search(db, jql, current_user=user, limit=1000)
            failed: list[dict] = []
            ok = 0
            for issue in rows:
                try:
                    issue_svc.transition_issue(db, user, issue.id, to_status, comment)
                    ok += 1
                except HTTPException as e:
                    failed.append({"issue_id": issue.id, "error": str(e.detail)})
            return {"total_matched": total, "succeeded": ok, "failed": failed}

    @mcp.tool(
        description=(
            "Bulk-assign every issue matching a JQL query to the given user. Pass `assignee=null` "
            "to unassign all matching issues. Like jira_bulk_transition, failures don't abort the batch."
        )
    )
    def jira_bulk_assign(
        jql: str,
        assignee: Optional[str],
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            rows, total = search(db, jql, current_user=user, limit=1000)
            failed: list[dict] = []
            ok = 0
            for issue in rows:
                try:
                    issue_svc.assign_issue(db, user, issue.id, assignee)
                    ok += 1
                except HTTPException as e:
                    failed.append({"issue_id": issue.id, "error": str(e.detail)})
            return {"total_matched": total, "succeeded": ok, "failed": failed}

    # ---- Sprints ---------------------------------------------------------

    @mcp.tool(description="List sprints, optionally filtered by project_key.")
    def jira_list_sprints(
        project_key: Optional[str] = None,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> list[dict]:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            return [_dump(SprintOut.model_validate(s)) for s in sprint_svc.list_sprints(db, project_key)]

    @mcp.tool(description="Get a single sprint by id.")
    def jira_get_sprint(
        sprint_id: str,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            return _dump(SprintOut.model_validate(sprint_svc.get_sprint(db, sprint_id)))

    @mcp.tool(
        description=(
            "List every issue currently in a sprint. Equivalent to "
            "`jira_search('sprint = <sprint_id>')` but cheaper and ordered by added_at."
        )
    )
    def jira_get_sprint_issues(
        sprint_id: str,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> list[dict]:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            sprint_svc.get_sprint(db, sprint_id)  # 404 if missing
            issues = (
                db.query(Issue)
                .join(SprintIssue, SprintIssue.issue_id == Issue.id)
                .filter(SprintIssue.sprint_id == sprint_id)
                .all()
            )
            return [_dump(issue_to_out(db, i)) for i in issues]

    @mcp.tool(
        description=(
            "Create a future sprint. `start_date` and `end_date` are optional ISO-8601 strings "
            "(e.g. '2026-06-01T00:00:00Z'); leave them null to create a sprint with no fixed dates "
            "that you'll start later with `jira_start_sprint`. Lead/admin only."
        )
    )
    def jira_create_sprint(
        project_key: str,
        name: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        goal: Optional[str] = None,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            s = sprint_svc.create_sprint(
                db, user, project_key=project_key, name=name,
                start_date=_parse_iso(start_date), end_date=_parse_iso(end_date),
                goal=goal,
            )
            return _dump(SprintOut.model_validate(s))

    @mcp.tool(
        description=(
            "Add a list of issue ids to a sprint. If an issue is already in another sprint within "
            "the same project, it is moved (with both sprint_removed and sprint_added activities)."
        )
    )
    def jira_add_issues_to_sprint(
        sprint_id: str,
        issue_ids: list[str],
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            s = sprint_svc.add_issues_to_sprint(db, user, sprint_id, issue_ids)
            return _dump(SprintOut.model_validate(s))

    @mcp.tool(
        description=(
            "Remove a list of issue ids from a sprint. Each removed issue is pushed back to the "
            "backlog. For single-issue moves prefer `jira_set_sprint(id, null)`."
        )
    )
    def jira_remove_issues_from_sprint(
        sprint_id: str,
        issue_ids: list[str],
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            s = sprint_svc.remove_issues_from_sprint(db, user, sprint_id, issue_ids)
            return _dump(SprintOut.model_validate(s))

    @mcp.tool(description="Start a sprint (move it from 'future' to 'active'). Lead/admin only.")
    def jira_start_sprint(
        sprint_id: str,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            s = sprint_svc.start_sprint(db, user, sprint_id)
            return _dump(SprintOut.model_validate(s))

    @mcp.tool(
        description=(
            "Complete a sprint. Unfinished issues are removed from the sprint; if `move_unfinished_to` "
            "is set, they're added to that target sprint instead. Lead/admin only."
        )
    )
    def jira_complete_sprint(
        sprint_id: str,
        move_unfinished_to: Optional[str] = None,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            s = sprint_svc.complete_sprint(db, user, sprint_id, move_unfinished_to)
            return _dump(SprintOut.model_validate(s))

    # ---- Boards ---------------------------------------------------------

    @mcp.tool(
        description=(
            "List boards, optionally filtered by project_key. Each board has an id, project_key, "
            "name, board_type ('scrum' or 'kanban'), and a filter_jql expression. Pass the id to "
            "`jira_get_board` for a column-by-column snapshot."
        )
    )
    def jira_list_boards(
        project_key: Optional[str] = None,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> list[dict]:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            return [
                {
                    "id": b.id, "project_key": b.project_key, "name": b.name,
                    "board_type": b.board_type, "filter_jql": b.filter_jql,
                }
                for b in board_svc.list_boards(db, project_key)
            ]

    @mcp.tool(description="Get a board snapshot - columns of cards filtered by board type and active sprint.")
    def jira_get_board(
        board_id: str,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            snap = snapshot_board(db, board_id)
            return {
                "board_id": snap.board.id, "project_key": snap.project.key,
                "board_type": snap.board.board_type,
                "active_sprint": _dump(SprintOut.model_validate(snap.active_sprint)) if snap.active_sprint else None,
                "columns": [
                    {
                        "status_name": c.status_name, "board_list": c.board_list, "category": c.category,
                        "cards": [_dump(issue_to_out(db, card.issue)) for card in c.cards],
                    }
                    for c in snap.columns
                ],
            }

    # ---- History ---------------------------------------------------------

    @mcp.tool(description="Get the activity history for an issue (newest first).")
    def jira_get_history(
        id: str,
        limit: int = 50,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> list[dict]:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            rows = history_for_issue(db, id, limit)
            return [_dump(ActivityOut.model_validate(a)) for a in rows]

    @mcp.tool(
        description=(
            "List @mentions of the current user across all issues, newest first. "
            "This is the agent-facing notifications inbox. Each result is an "
            "'mentioned' activity row whose `to_value` is the recipient, "
            "`actor_id` is the comment author, and `comment_body` is the comment."
        )
    )
    def jira_my_mentions(
        limit: int = 50,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> list[dict]:
        from app.models import Activity
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            rows = (
                db.query(Activity)
                .filter(Activity.action == "mentioned", Activity.to_value == user.id)
                .order_by(Activity.created_at.desc())
                .limit(limit)
                .all()
            )
            return [_dump(ActivityOut.model_validate(a)) for a in rows]

    # ---- Clock -----------------------------------------------------------

    @mcp.tool(
        description=(
            "Read the environment's universal clock (mode + current 'now'). "
            "Researchers can pin the clock via POST /api/admin/clock or the "
            "JP_CLOCK env var so JQL like 'updated > -7d' returns a stable set."
        )
    )
    def jira_get_clock(
        auth_token: Optional[str] = None, ctx: Context = None
    ) -> dict:
        from app import clock as _clock
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            return _clock.describe()

    # ---- Users / filters / utility -------------------------------------

    @mcp.tool(description="List all users (for picking assignees).")
    def jira_list_users(
        auth_token: Optional[str] = None, ctx: Context = None
    ) -> list[dict]:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            users = db.query(User).order_by(User.name).all()
            return [_dump(UserOut.model_validate(u)) for u in users]

    @mcp.tool(description="Get one user by id.")
    def jira_get_user(
        user_id: str,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            u = db.query(User).filter(User.id == user_id).one_or_none()
            if u is None:
                raise HTTPException(404, f"User '{user_id}' not found.")
            return _dump(UserOut.model_validate(u))

    @mcp.tool(description="List saved filters available to the current user (shared + own).")
    def jira_list_filters(
        auth_token: Optional[str] = None, ctx: Context = None
    ) -> list[dict]:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            rows = (
                db.query(SavedFilter)
                .filter((SavedFilter.shared.is_(True)) | (SavedFilter.owner_id == user.id))
                .order_by(SavedFilter.name)
                .all()
            )
            return [_dump(SavedFilterOut.model_validate(r)) for r in rows]

    @mcp.tool(
        description=(
            "Get one saved filter by id or name. Useful for resolving a name to its JQL before "
            "running `jira_search`."
        )
    )
    def jira_get_filter(
        filter_id_or_name: str,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            _resolve(db, auth_token, ctx)
            f = db.query(SavedFilter).filter(SavedFilter.id == filter_id_or_name).one_or_none()
            if f is None:
                f = (
                    db.query(SavedFilter)
                    .filter(SavedFilter.name == filter_id_or_name)
                    .one_or_none()
                )
            if f is None:
                raise HTTPException(404, f"Saved filter '{filter_id_or_name}' not found.")
            return _dump(SavedFilterOut.model_validate(f))

    @mcp.tool(
        description=(
            "Create a saved filter visible to the current user (and optionally others via "
            "`shared=true`). The filter's `jql` is stored verbatim and can be referenced later as "
            "`filter = \"<name>\"` inside another JQL query."
        )
    )
    def jira_create_filter(
        name: str,
        jql: str,
        description: Optional[str] = None,
        shared: bool = True,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        import uuid as _uuid
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            f = SavedFilter(
                id=f"filter_{_uuid.uuid4().hex[:12]}",
                name=name, owner_id=user.id, jql=jql,
                description=description, shared=shared,
            )
            db.add(f)
            db.flush()
            return _dump(SavedFilterOut.model_validate(f))

    # ---- Clock control & admin --------------------------------------------

    @mcp.tool(
        description=(
            "Reconfigure the environment's universal clock at runtime. Admin role required. "
            "Modes:\n"
            "- 'real': restore wall-clock time.\n"
            "- 'frozen': pin to `at` (ISO-8601 string, e.g. '2026-05-27T12:00:00Z').\n"
            "- 'offset': run on wall clock + `seconds` (positive = future).\n"
            "- 'advance': bump the current clock forward by `seconds`.\n"
            "Returns the new clock state (same shape as `jira_get_clock`)."
        )
    )
    def jira_set_clock(
        mode: str,
        at: Optional[str] = None,
        seconds: Optional[float] = None,
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        from app import clock as _clock
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            from app.services import permissions
            permissions.require(db, user, "admin.reset")
            m = mode.lower()
            if m == "real":
                _clock.unfreeze()
            elif m == "frozen":
                if not at:
                    raise HTTPException(422, "mode='frozen' requires 'at' (ISO timestamp).")
                _clock.freeze(at)
            elif m == "offset":
                if seconds is None:
                    raise HTTPException(422, "mode='offset' requires 'seconds'.")
                _clock.set_offset(seconds)
            elif m == "advance":
                if seconds is None:
                    raise HTTPException(422, "mode='advance' requires 'seconds'.")
                _clock.advance(seconds)
            else:
                raise HTTPException(
                    422,
                    f"Unknown clock mode '{mode}'. Use one of: real, frozen, offset, advance.",
                )
            return _clock.describe()

    @mcp.tool(
        description=(
            "Restore state.db from the immutable seed.db. All mutations since the last seed rebuild "
            "are discarded. Admin role required. Returns `{success, message}`."
        )
    )
    def jira_admin_reset(
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            from app.services import permissions
            permissions.require(db, user, "admin.reset")
        # Reset happens outside the session_scope to avoid mid-transaction file swap
        from app.db import reset_state_from_seed
        reset_state_from_seed()
        return _dump(AdminResetOut(success=True, message="state.db restored from seed.db."))

    @mcp.tool(
        description=(
            "Rebuild seed.db from the YAML fixtures and Python content modules, then copy to "
            "state.db. Use this after editing fixtures; otherwise prefer `jira_admin_reset`. "
            "Admin role required."
        )
    )
    def jira_admin_reseed(
        auth_token: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        with session_scope() as db:
            user = _resolve(db, auth_token, ctx)
            from app.services import permissions
            permissions.require(db, user, "admin.reseed")
        from app.seed.builder import rebuild
        rebuild()
        return _dump(AdminResetOut(success=True, message="seed.db rebuilt from fixtures and applied."))


# ---- Inline reimplementation of /api/projects/{key}/summary -----------
# (Kept here because the REST handler depends on Depends() which we can't call
# directly from MCP without fabricating a request context.)


def _project_summary_inline(db, key: str) -> ProjectSummaryOut:
    from sqlalchemy import func

    from app.models import Activity, Project, Sprint, SprintIssue

    project = project_svc.get_project(db, key)
    total = db.query(Issue).filter(Issue.project_key == key).count()
    rows = (
        db.query(WorkflowStatus.name, func.count(Issue.id))
        .join(Issue, Issue.status_id == WorkflowStatus.id)
        .filter(Issue.project_key == key)
        .group_by(WorkflowStatus.name)
        .all()
    )
    by_status = {n: c for n, c in rows}
    rows = (
        db.query(Issue.priority, func.count(Issue.id))
        .filter(Issue.project_key == key)
        .group_by(Issue.priority)
        .all()
    )
    by_priority = {p: c for p, c in rows}
    rows = (
        db.query(Issue.owner, func.count(Issue.id))
        .filter(Issue.project_key == key)
        .group_by(Issue.owner)
        .all()
    )
    by_assignee = {(owner or "unassigned"): cnt for owner, cnt in rows}
    active_sprint = (
        db.query(Sprint).filter(Sprint.project_key == key, Sprint.state == "active").first()
    )
    progress = None
    if active_sprint is not None:
        sub = (
            db.query(WorkflowStatus.category, func.count(Issue.id))
            .join(Issue, Issue.status_id == WorkflowStatus.id)
            .join(SprintIssue, SprintIssue.issue_id == Issue.id)
            .filter(SprintIssue.sprint_id == active_sprint.id)
            .group_by(WorkflowStatus.category)
            .all()
        )
        progress = {c: n for c, n in sub}
    recent = (
        db.query(Activity)
        .join(Issue, Issue.id == Activity.issue_id, isouter=True)
        .filter(Issue.project_key == key)
        .order_by(Activity.created_at.desc())
        .limit(15)
        .all()
    )
    return ProjectSummaryOut(
        project=ProjectOut.model_validate(project),
        total_issues=total,
        by_status=by_status,
        by_priority=by_priority,
        by_assignee=by_assignee,
        active_sprint=SprintOut.model_validate(active_sprint) if active_sprint else None,
        active_sprint_progress=progress,
        recent_activity=[ActivityOut.model_validate(a) for a in recent],
    )
