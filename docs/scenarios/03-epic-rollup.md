# Scenario 3: Epic Roll-Up and the Done Guard

> Exercises: parent/child issue hierarchy, the workflow Epic guard, audit log.

## Goal

A PM tries to "wrap" an Epic by transitioning it to `Done`. The workflow engine
refuses unless every child story is itself `Done`. Once the PM closes out the
remaining child, the Epic transitions cleanly.

## Preconditions

- Epic `SCRUM-1` ("Push Notifications v2") exists with multiple child stories,
  at least one of which is *not* in `Done`.

## Walkthrough (REST)

```bash
TOKEN=$ADMIN
BASE=http://localhost:8080/api
EPIC=SCRUM-1

# 1. Attempt to close epic prematurely
curl -i -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"to_status":"Done"}' $BASE/issues/$EPIC/transitions
# -> 422 with detail: "Epic cannot move to Done while 1 child issue(s) are unresolved."

# 2. Finish the child first
CHILDREN=$(curl -sH "Authorization: Bearer $TOKEN" $BASE/issues/$EPIC | jq -r '.children[].id')
LAST=$(echo "$CHILDREN" | tail -1)
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"to_status":"Done"}' $BASE/issues/$LAST/transitions

# 3. Now the epic transitions
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"to_status":"Done"}' $BASE/issues/$EPIC/transitions
```

## MCP equivalent

```python
# The MCP tool re-raises the same ToolError with detail message preserved
try:
    mcp.call_tool("jira_transition_issue", {"auth_token": ADMIN, "id": "SCRUM-1", "to_status": "Done"})
except ToolError as e:
    assert "Epic cannot move to Done" in str(e)
```

## Verifier checks

1. The first transition attempt left `SCRUM-1.status_id` unchanged.
2. No `activities` row was written for the failed attempt — guards must be
   silent on rejection.
3. After completing the child, the epic's `status_id` is `status_scrum_done`
   and `resolution = "Fixed"`.
4. `activities` for the epic contains the expected `transitioned` row.

## Edge cases worth testing

- The guard message includes the **count** of unresolved children, so an agent
  can decide whether to recurse or punt.
- Tasks parented under stories (sub-tasks) inherit the same restriction at the
  story level (story cannot Done with open sub-tasks).
- Reopening the epic from `Done` to `In Progress` is allowed unconditionally.
