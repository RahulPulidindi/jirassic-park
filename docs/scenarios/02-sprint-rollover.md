# Scenario 2: Sprint Rollover

> Exercises: sprint lifecycle, "carry to next sprint" semantics, board snapshots, history.

## Goal

A scrum master closes Sprint 23 partway through. Two issues are still in
progress; they roll over into Sprint 24. The dashboard reflects the new active
sprint.

## Preconditions

- `SCRUM` project has at least one `active` sprint (Sprint 23) and one `future`
  sprint (Sprint 24) — present in seed data.
- The active sprint has at least two issues not in `Done`.

## Walkthrough (REST)

```bash
TOKEN=$ADMIN
BASE=http://localhost:8080/api

# Discover the active sprint
ACTIVE=$(curl -sH "Authorization: Bearer $TOKEN" "$BASE/sprints?project_key=SCRUM&state=active" | jq -r '.[0].id')
NEXT=$(curl -sH "Authorization: Bearer $TOKEN" "$BASE/sprints?project_key=SCRUM&state=future" | jq -r '.[0].id')

# Snapshot the board pre-close
curl -sH "Authorization: Bearer $TOKEN" "$BASE/boards/board_scrum/snapshot?sprint_id=$ACTIVE" > /tmp/pre.json

# Complete sprint; unfinished issues move to NEXT
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"move_unfinished_to\":\"$NEXT\"}" $BASE/sprints/$ACTIVE/complete

# Activate next sprint
curl -s -X POST -H "Authorization: Bearer $TOKEN" $BASE/sprints/$NEXT/start
```

## MCP equivalent

```python
mcp.call_tool("jira_complete_sprint", {"auth_token": ADMIN, "id": ACTIVE, "move_unfinished_to": NEXT})
mcp.call_tool("jira_start_sprint",    {"auth_token": ADMIN, "id": NEXT})
```

## Verifier checks

1. `ACTIVE.state == "closed"`, `ACTIVE.completed_at` set.
2. `NEXT.state == "active"`, `NEXT.started_at` set.
3. For every issue that was in `ACTIVE` with status not in
   (`Done`, `Resolved`, `Closed`):
   - `sprint_issues` no longer has `(issue, ACTIVE)`.
   - `sprint_issues` now has `(issue, NEXT)`.
4. For every issue that was in `ACTIVE` with `Done` status: still associated
   to `ACTIVE` (not moved).
5. `activities` for each rolled-over issue contains a row
   `(action="sprint_changed", from_value=ACTIVE, to_value=NEXT)`.

## Edge cases worth testing

- `complete` without `move_unfinished_to` should leave unfinished issues
  unassigned to any sprint (this is the conservative default).
- `start` on a `closed` sprint should 422.
- A non-lead user calling `complete` should 403 (RBAC).
