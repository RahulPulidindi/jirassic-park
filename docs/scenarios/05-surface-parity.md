# Scenario 5: REST/MCP Surface Parity (the "agent or human?" property)

> Exercises: services-as-source-of-truth invariant, identical audit + state output
> from REST and MCP.

## Goal

For every mutation an agent can perform via MCP, a human can perform the
identical mutation via REST and end up at the same DB state. This is enforced
both by code structure (REST handlers and MCP tools delegate to the same
`app.services.*` functions) and by tests.

## How the invariant holds in code

```
HTTP request                MCP tool call
     |                           |
     v                           v
[FastAPI route] --,           ,-- [FastMCP tool]
                  v           v
              app.services.<entity>.<verb>(...)
                          |
                          v
                  SQLAlchemy session + activity row
```

Both surfaces ultimately reach a single function in `app/services/`. Anything
that mutates DB state goes through:

- `issues.create_issue`, `issues.update_issue`
- `issues.transition_issue`
- `issues.assign_issue`
- `issues.add_comment`
- `issues.link_issues`, `issues.unlink_issues`
- `issues.add_label`, `issues.remove_label`
- `sprints.start_sprint`, `sprints.complete_sprint`, `sprints.add_to_sprint`
- `projects.create_project`, `projects.update_project`
- `auth` (read-only): both surfaces resolve the same `users.api_token`.

## Verifier checks (mirrored in `tests/test_surface_parity.py`)

The parity test pattern is:

```python
state_via_rest = run_ops_via_rest(client, ops)
reset_state_from_seed()                # bring DB back to baseline
state_via_mcp = run_ops_via_mcp(mcp,  ops)
assert state_via_rest == state_via_mcp
```

`state` includes:

1. The `issues` row (every column except auto-timestamps).
2. The full `activities` list (ordered, normalized to exclude id + created_at).
3. The full `comments` list (author, body, ordered).
4. `issue_links` rows for any involved issues.
5. `sprint_issues` rows for any involved issues.
6. `issue_labels` rows for any involved issues.

If a parity test ever fails, that's a sign a code path drifted (i.e., a route
or tool stopped delegating to `services` and started mutating DB state directly).

## Manual parity smoke (one-liner)

```bash
# Create an issue via REST
ID=$(curl -s -H "Authorization: Bearer $ADMIN" -d '{"project_key":"PLAT","summary":"hi"}' \
  -H 'Content-Type: application/json' http://localhost:8080/api/issues | jq -r .id)
# Read it back via MCP
python -c "
import asyncio
from mcp.server.fastmcp import FastMCP
from app.mcp.tools_impl import register
m=FastMCP('x'); register(m)
print(asyncio.run(m.call_tool('jira_get_issue', {'auth_token':'admin-token-jurassic','id':'$ID'}))[0].text)
"
```
