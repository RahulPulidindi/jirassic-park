# MCP Tool Catalog

The MCP server is mounted at `http://localhost:8080/mcp/` (note the trailing
slash — Streamable HTTP requires it). It uses the standard Streamable HTTP
MCP transport, so any MCP client (Claude Desktop, your own
`mcp.ClientSession`, etc.) can connect.

Quickest smoke test, with the server running:

```bash
make mcp-demo   # or:  python backend/scripts/mcp_demo.py
```

This drives `initialize → list_tools → whoami → summarize_project → search
→ create_issue → transition_issue → get_history → (negative)` and prints
the result of each call. Exits non-zero on any failure.

### Driving the MCP from a real LLM

`make agent-demo` (or `backend/scripts/agent_demo.py`) connects an
**Anthropic Claude** model to this same `/mcp/` endpoint and gives it the
goal *"escalate customer ticket SUP-1 to engineering"* — nothing else. The
agent discovers the tool catalog, plans a multi-step workflow, executes it
through MCP, and reports back. See the
[Agent demo section in the README](../README.md#agent-demo-real-llm-driving-the-mcp).
Requires `ANTHROPIC_API_KEY`.

## Authentication

Each tool accepts an `auth_token` argument, **or** you can pass the bearer
token in the `Authorization` header at the transport level (the MCP
context exposes the HTTP request to the server). All tools resolve the
authenticated user from one of those two sources before doing anything
else.

If neither is provided (or the token is unknown), the tool raises
`ToolError("Authentication required: pass auth_token or Authorization header.")`.

## Tool reference

> **Parity invariant.** Every REST endpoint has a paired MCP tool that calls
> the same service-layer function. The table below is grouped by surface to
> make that easy to verify; see also `backend/tests/test_surface_parity.py`
> which asserts byte-identical state and audit-log rows for every paired
> operation.

### Orientation / reads

| Tool                              | REST analog                                  | Description                                                                |
| --------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------- |
| `jira_whoami`                     | `GET /auth/me`                               | Return the current authenticated user.                                     |
| `jira_get_clock`                  | `GET /clock`                                 | Read the env's universal clock (mode + current `now`).                     |
| `jira_my_mentions`                | `GET /users/me/mentions`                     | `@`-mentions inbox for the current user (notifications).                   |
| `jira_search`                     | `GET /search?jql=...`                        | Run a JQL-lite query. Returns `{total, issues}`.                           |

### Projects & workflows

| Tool                              | REST analog                                  | Description                                                                |
| --------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------- |
| `jira_list_projects`              | `GET /projects`                              | List visible projects.                                                     |
| `jira_get_project`                | `GET /projects/{key}`                        | Return one project.                                                        |
| `jira_create_project`             | `POST /projects`                             | Create a project (admin only).                                             |
| `jira_update_project`             | `PATCH /projects/{key}`                      | Update project metadata (admin only).                                      |
| `jira_get_workflow`               | `GET /projects/{key}/workflow`               | Discover statuses + transitions for a project's workflow.                  |
| `jira_summarize_project`          | `GET /projects/{key}/summary`                | Counts by status, sprint progress, top contributors.                       |

### Issues

| Tool                              | REST analog                                  | Description                                                                |
| --------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------- |
| `jira_get_issue`                  | `GET /issues/{id}`                           | One issue with comments, history, links, watchers, allowed transitions.    |
| `jira_create_issue`               | `POST /issues`                               | Create a new issue.                                                        |
| `jira_update_issue`               | `PATCH /issues/{id}`                         | Patch an existing issue.                                                   |
| `jira_transition_issue`           | `POST /issues/{id}/transitions`              | Move an issue to a new status; optional `comment`.                         |
| `jira_assign_issue`               | `POST /issues/{id}/assign`                   | Assign to a user or unassign.                                              |
| `jira_set_sprint`                 | `PUT /issues/{id}/sprint`                    | Move to a sprint or to backlog (`sprint_id: null`).                        |
| `jira_add_comment`                | `POST /issues/{id}/comments`                 | Add a (threaded) comment; parses `@mentions`.                              |
| `jira_list_comments`              | `GET /issues/{id}/comments`                  | List all comments on an issue.                                             |
| `jira_update_comment`             | `PATCH /issues/{id}/comments/{comment_id}`   | Edit a comment (author or admin); re-parses `@mentions`, only notifies new tags. |
| `jira_delete_comment`             | `DELETE /issues/{id}/comments/{comment_id}`  | Delete a comment (author or admin); audit row retains the old body.        |
| `jira_link_issues`                | `POST /issues/{id}/links`                    | Add a link (`blocks`, `relates`, `duplicates`, `clones`, `causes`).        |
| `jira_unlink_issues`              | `DELETE /issues/{id}/links`                  | Remove an existing link (idempotent).                                      |
| `jira_add_label`                  | `POST /issues/{id}/labels`                   | Add a label (created on the fly if new).                                   |
| `jira_remove_label`               | `DELETE /issues/{id}/labels/{label}`         | Remove a label (idempotent).                                               |
| `jira_watch_issue`                | `POST /issues/{id}/watch`                    | Subscribe the current user to an issue.                                    |
| `jira_unwatch_issue`              | `DELETE /issues/{id}/watch`                  | Unsubscribe (idempotent).                                                  |
| `jira_get_history`                | `GET /issues/{id}/history`                   | Activity history (newest first).                                           |

### Sprints

| Tool                              | REST analog                                  | Description                                                                |
| --------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------- |
| `jira_list_sprints`               | `GET /sprints`                               | List sprints, optionally filtered by project_key.                          |
| `jira_get_sprint`                 | `GET /sprints/{id}`                          | One sprint by id.                                                          |
| `jira_get_sprint_issues`          | `GET /sprints/{id}/issues`                   | Every issue currently in a sprint.                                         |
| `jira_create_sprint`              | `POST /sprints`                              | Create a future sprint (lead/admin).                                       |
| `jira_start_sprint`               | `POST /sprints/{id}/start`                   | future → active.                                                           |
| `jira_complete_sprint`            | `POST /sprints/{id}/complete`                | active → closed, optional rollover target.                                 |
| `jira_add_issues_to_sprint`       | `POST /sprints/{id}/issues`                  | Add a list of issues to a sprint.                                          |
| `jira_remove_issues_from_sprint`  | `DELETE /sprints/{id}/issues`                | Bulk-remove issues (push back to backlog).                                 |

### Boards & filters

| Tool                              | REST analog                                  | Description                                                                |
| --------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------- |
| `jira_list_boards`                | `GET /boards`                                | List boards, optionally filtered by project_key.                           |
| `jira_get_board`                  | `GET /boards/{id}`                           | Board snapshot (columns of cards).                                         |
| `jira_list_filters`               | `GET /filters`                               | Saved filters visible to the current user.                                 |
| `jira_get_filter`                 | `GET /filters/{id}`                          | Look up a saved filter by id or name.                                      |
| `jira_create_filter`              | `POST /filters`                              | Create a saved filter.                                                     |

### Users

| Tool                              | REST analog                                  | Description                                                                |
| --------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------- |
| `jira_list_users`                 | `GET /users`                                 | List all users.                                                            |
| `jira_get_user`                   | `GET /users/{id}`                            | One user by id.                                                            |

### Bulk operations

| Tool                              | REST analog                                  | Description                                                                |
| --------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------- |
| `jira_bulk_transition`            | `POST /search/bulk_transition`               | Run a JQL query, transition every match. Returns `{succeeded, failed}`.    |
| `jira_bulk_assign`                | `POST /search/bulk_assign`                   | Run a JQL query, reassign every match.                                     |

### Admin (admin role required)

| Tool                              | REST analog                                  | Description                                                                |
| --------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------- |
| `jira_set_clock`                  | `POST /admin/clock`                          | Reconfigure the universal clock (real/frozen/offset/advance).              |
| `jira_admin_reset`                | `POST /admin/reset`                          | Restore `state.db` from immutable `seed.db`.                               |
| `jira_admin_reseed`               | `POST /admin/reseed`                         | Rebuild `seed.db` from fixtures and apply.                                 |

## Tool error model

All tools raise `mcp.server.fastmcp.exceptions.ToolError(message)` for any
non-2xx outcome from the underlying service. The message mirrors the REST
`detail` field exactly, so an agent gets:

```
ToolError: Cannot transition from 'Backlog' to 'In Review'. Allowed next statuses: 'In Progress', 'To Do'.
```

This is by design — the wording is the same on both surfaces so an agent
trained against one surface can use the other interchangeably.

## End-to-end example (in-process)

```python
import asyncio, json
from mcp.server.fastmcp import FastMCP
from app.mcp.tools_impl import register

mcp = FastMCP("demo")
register(mcp)

async def main():
    # 1. Orient
    me = await mcp.call_tool("jira_whoami", {"auth_token": "admin-token-jurassic"})
    print("Logged in as:", json.loads(me[0].text)["name"])

    # 2. Find a high-priority bug
    out = await mcp.call_tool("jira_search", {
        "auth_token": "admin-token-jurassic",
        "jql": "priority = Highest AND status != Done",
        "limit": 5,
    })
    issues = json.loads(out[0].text)["issues"]
    print(f"Found {len(issues)} hot bugs")

    if issues:
        iid = issues[0]["id"]
        # 3. Reassign and progress
        await mcp.call_tool("jira_assign_issue", {
            "auth_token": "admin-token-jurassic",
            "id": iid,
            "assignee": "user_priya_iyer",
        })
        await mcp.call_tool("jira_transition_issue", {
            "auth_token": "admin-token-jurassic",
            "id": iid,
            "to_status": "In Progress",
            "comment": "Picked up by Priya.",
        })

asyncio.run(main())
```

## MCP client compatibility

The conventions used here are designed for broad MCP client compatibility:

- Tools are prefixed `jira_*`.
- Inputs and outputs are plain JSON (no opaque handles).
- Every mutating tool's output is the *full updated entity*, so a verifier
  can score against the returned object without a follow-up read.
- Every mutating tool writes one or more rows in `activities`, with a
  schema (`field`, `from_value`, `to_value`, `actor_id`) suitable for
  scoring "did the agent take the right *path*?" rather than only the
  final state.
