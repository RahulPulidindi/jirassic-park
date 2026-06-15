# Scenario 1: Triage and Resolve a Customer-Reported Bug

> Exercises: workflow state machine, comments, assignment, audit log, RBAC, both surfaces.

## Goal

A new customer-reported bug lands in the Support project (`SUP`). An on-call
engineer triages it, escalates it to the Platform project (`PLAT`) by linking,
fixes the underlying issue, and closes the support ticket once the fix ships.

## Preconditions

- Fresh `state.db` (or `make reset`).
- `admin-token-jurassic` exists and has admin role.
- `user_devon_lee` is a lead on `SUP`.
- `user_marcus_obrien` is a lead on `PLAT`.

## Walkthrough (REST)

```bash
TOKEN_DEVON="token_devon_lee"
TOKEN_MARCUS="token_marcus_obrien"
BASE=http://localhost:8080/api

# 1. Customer files the bug
SUP_ID=$(curl -s -H "Authorization: Bearer $TOKEN_DEVON" -H 'Content-Type: application/json' \
  -d '{"project_key":"SUP","issue_type":"Bug","summary":"Mobile app crash on launch (iOS 17)","priority":"High","labels":["customer-reported","ios"]}' \
  $BASE/issues | jq -r .id)

# 2. Triage: assign to Devon and move to Triaged
curl -s -X POST -H "Authorization: Bearer $TOKEN_DEVON" -H 'Content-Type: application/json' \
  -d "{\"assignee\":\"user_devon_lee\"}" $BASE/issues/$SUP_ID/assign
curl -s -X POST -H "Authorization: Bearer $TOKEN_DEVON" -H 'Content-Type: application/json' \
  -d '{"to_status":"Triaged","comment":"Confirmed reproducible on iOS 17.2."}' \
  $BASE/issues/$SUP_ID/transitions

# 3. Open a Platform bug for the underlying defect and link them
PLAT_ID=$(curl -s -H "Authorization: Bearer $TOKEN_MARCUS" -H 'Content-Type: application/json' \
  -d '{"project_key":"PLAT","issue_type":"Bug","summary":"Push notification handler crashes on cold start"}' \
  $BASE/issues | jq -r .id)
# Link types accepted: blocks, relates, duplicates, clones, causes.
# PLAT-X causes the SUP ticket; we record that on the PLAT side.
curl -s -X POST -H "Authorization: Bearer $TOKEN_MARCUS" -H 'Content-Type: application/json' \
  -d "{\"target\":\"$SUP_ID\",\"link_type\":\"causes\"}" $BASE/issues/$PLAT_ID/links

# 4. Platform fixes PLAT_ID
curl -s -X POST -H "Authorization: Bearer $TOKEN_MARCUS" -H 'Content-Type: application/json' \
  -d '{"to_status":"In Progress"}' $BASE/issues/$PLAT_ID/transitions
curl -s -X POST -H "Authorization: Bearer $TOKEN_MARCUS" -H 'Content-Type: application/json' \
  -d '{"to_status":"Done","comment":"Patched in #4321, ship in 4.2.1."}' $BASE/issues/$PLAT_ID/transitions

# 5. Devon closes the support ticket
curl -s -X POST -H "Authorization: Bearer $TOKEN_DEVON" -H 'Content-Type: application/json' \
  -d '{"to_status":"Working"}' $BASE/issues/$SUP_ID/transitions
curl -s -X POST -H "Authorization: Bearer $TOKEN_DEVON" -H 'Content-Type: application/json' \
  -d '{"to_status":"Resolved","comment":"Fix shipped in 4.2.1."}' $BASE/issues/$SUP_ID/transitions
```

## MCP equivalent (one tool per action)

```python
mcp.call_tool("jira_create_issue", {"auth_token": "token_devon_lee", "project_key": "SUP", "issue_type": "Bug", ...})
mcp.call_tool("jira_assign_issue", {"auth_token": "token_devon_lee", "id": SUP_ID, "assignee": "user_devon_lee"})
mcp.call_tool("jira_transition_issue", {"auth_token": "token_devon_lee", "id": SUP_ID, "to_status": "Triaged", "comment": "Confirmed reproducible on iOS 17.2."})
mcp.call_tool("jira_link_issues", {"auth_token": "token_marcus_obrien", "source": PLAT_ID, "target": SUP_ID, "link_type": "causes"})
# ...etc.
```

## Verifier checks

A scoring agent (verifier) for this scenario should assert all
of the following against `state.db`:

1. `SUP_ID` exists, has `status_id = status_sup_resolved`, `priority = High`,
   labels include `customer-reported` and `ios`.
2. `PLAT_ID` exists, has `status_id = status_scrum_done`,
   `resolution = "Fixed"`.
3. `issue_links` contains exactly one row `(PLAT_ID, SUP_ID, "causes")`.
4. `activities` for `SUP_ID` contains, in order: `created`, `assigned`,
   `transitioned (Open->Triaged)`, `commented`,
   `transitioned (Triaged->Working)`, `transitioned (Working->Resolved)`,
   `commented`. `PLAT_ID` activities additionally contain `linked
   (causes:SUP_ID)`.
5. Both surfaces produce identical activity streams (parity test enforces).

## Edge cases worth testing

- Trying `to_status=Done` on `SUP_ID` should 422 (kanban has no `Done`).
- Devon (lead on SUP, not PLAT) tries to transition `PLAT_ID` — should 403.
- Linking a non-existent issue should 404.
