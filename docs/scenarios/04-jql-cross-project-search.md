# Scenario 4: JQL Searches and Bulk Operations

> Exercises: JQL-lite parser, saved filters, bulk transitions, history.

## Goal

A platform lead wants to triage every high-severity bug across all projects
that's older than 14 days, then bulk-reassign them to a specific engineer.

## Preconditions

- The seeded `"Stale P0/P1"` saved filter is present with JQL:
  `priority in ("Highest", "High") AND status != "Done" AND updated <= -14d`.
- Multiple matching issues across SCRUM/PLAT/SUP.

## Walkthrough (REST)

```bash
TOKEN=$ADMIN
BASE=http://localhost:8080/api

# 1. Search via saved filter
curl -sH "Authorization: Bearer $TOKEN" "$BASE/search?jql=filter%20%3D%20%22Stale%20P0/P1%22&limit=200" \
  | jq -r '.issues[].id' > /tmp/stale.txt

# 2. Bulk reassign to user_priya_iyer
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"jql\":\"filter = \\\"Stale P0/P1\\\"\",\"assignee\":\"user_priya_iyer\"}" \
  $BASE/search/bulk_assign

# 3. For SCRUM-only ones, bulk-move them to In Progress
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"jql":"project = SCRUM AND filter = \"Stale P0/P1\"", "to_status": "In Progress"}' \
  $BASE/search/bulk_transition
```

## MCP equivalent

```python
mcp.call_tool("jira_search",            {"auth_token": ADMIN, "jql": 'filter = "Stale P0/P1"', "limit": 200})
mcp.call_tool("jira_bulk_assign",       {"auth_token": ADMIN, "jql": 'filter = "Stale P0/P1"', "assignee": "user_priya_iyer"})
mcp.call_tool("jira_bulk_transition",   {"auth_token": ADMIN, "jql": 'project = SCRUM AND filter = "Stale P0/P1"', "to_status": "In Progress"})
```

## Verifier checks

1. Every issue id returned by the search matches the WHERE predicate:
   - `priority in ("Highest","High")`
   - `issue_type = "Bug"`
   - `(now - updated_at).days >= 14`
2. After bulk assign, every matching issue has `owner = "user_priya_iyer"`
   and an `assigned` activity row with `actor_id = ADMIN`.
3. After bulk transition, every matching SCRUM issue has
   `status_id = status_scrum_inprogress` and a `transitioned` activity row.
4. Issues for which a transition was **illegal** (e.g. wrong workflow) are
   reported in the response's `skipped` list, not silently ignored.

## JQL coverage check

A separate JQL parser test (`tests/test_jql_parser.py`) verifies the
following productions parse and execute:

| Production                                           | Example                                          |
| ---------------------------------------------------- | ------------------------------------------------ |
| Field equality / inequality                          | `project = SCRUM`, `status != Done`              |
| `IN` / `NOT IN` lists                                | `priority in (Highest, High)`                    |
| Quoted and bareword values (including hyphenated)    | `labels = customer-reported`                     |
| Functions                                            | `currentUser()`, `unassigned()`, `now()`         |
| Relative dates                                       | `created >= -7d`, `updated <= -30d`              |
| Full-text                                            | `text ~ "login"`                                 |
| Boolean composition with precedence                  | `(P AND Q) OR R`, `NOT (... )`                   |
| Saved filter expansion                               | `filter = "Bugs assigned to me"`                 |
| Cross-table joins (labels, sprints)                  | `labels in (ios, android)`, `sprint = "..."`    |
| `ORDER BY` with multi-field, ASC/DESC                | `ORDER BY priority DESC, created ASC`            |
