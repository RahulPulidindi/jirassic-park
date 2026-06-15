# Fidelity: What We Model and What We Don't

This document is the contract between "real Jira" and "Jirassic Park" — a
checklist of which behaviors an agent or human can reasonably expect to
generalize from this environment to the real product, and which behaviors
are intentionally simpler.

## What we model with high fidelity

| Concept | How |
| ------- | --- |
| Projects, keys (`PLAT`, `SCRUM`, ...), per-project leads and members | `Project`, `User`, lead column + membership table |
| Issue types (Epic, Story, Task, Sub-task, Bug, Incident, Spike) | `Issue.issue_type`, parent/child hierarchy via `parent_id` and `epic_id` |
| Priorities (Highest → Lowest) and per-priority ordering | `Issue.priority` + JQL `ORDER BY priority DESC` |
| Statuses + named workflow transitions | `WorkflowStatus`, `WorkflowTransition`. Two workflows seeded: `software-scrum` and `support-kanban`. |
| Workflow guards (e.g. Epic blocks Done if children open) | `app.services.workflows.evaluate_guards` |
| Resolutions auto-set on entering Done, cleared on leaving | service handles this transparently |
| Comments (threaded via `parent_comment_id`) | `Comment` model |
| Labels | `Label` + `IssueLabel` association, plus dynamic creation on first use |
| Issue links (`blocks`, `blocked_by`, `relates_to`, `caused_by`, `duplicates`) | `IssueLink` |
| Watchers and votes | `Watcher`, `Vote` |
| Custom fields | `CustomField`, `CustomFieldValue` (per project) |
| Sprints with `future`/`active`/`closed` lifecycle | `Sprint`, plus dates |
| Sprint membership and rollover | `SprintIssue`, `complete_sprint(move_unfinished_to=...)` |
| Boards (scrum & kanban) | `Board` + `board_list` column on `WorkflowStatus`. The board view reads `Issue.board_list` directly so it cannot drift from status. |
| Saved JQL filters (shared and private) | `SavedFilter` |
| Activity history (every mutation logs a row) | `Activity` table, `app.services.history` |
| API tokens per user (bearer auth) | `User.api_token` |
| Admin reset / reseed | `/api/admin/reset`, file-copy of `seed.db` → `state.db` |

## JQL fidelity

We implement a faithful subset. Things that work:

- `field = value`, `field != value`, `field IN (...)`, `field NOT IN (...)`
- Boolean composition `AND`, `OR`, `NOT`, parentheses, full precedence
- Functions: `currentUser()`, `unassigned()`, `now()`
- Relative dates: `-7d`, `-2w`, `-3m`, `-1y`
- Full-text: `text ~ "substring"` against summary + description
- Cross-table joins: `labels`, `sprint`
- Saved filter expansion: `filter = "name"`
- Multi-key ordering: `ORDER BY priority DESC, created ASC`
- Bareword values with hyphens (`labels = customer-reported`) and quoted
  strings (`status = "In Progress"`)

Things we deliberately leave out:

- `WAS`, `CHANGED`, `BEFORE`, `AFTER` — these query the activity log
  rather than current state. Add a `historical:` JQL extension if needed.
- Custom field references by id (`cf[10010]`). We expose custom fields by
  human-readable key instead (`severity = "Sev-1"`).

If a query fails to parse, the response is HTTP 400 with the position of
the failing token, e.g. `JQL parse error: unexpected char '#' at pos 12`.

## What we don't model

| Concept | Why not |
| ------- | ------- |
| OAuth / SSO | Bearer tokens are sufficient for agent testing; tokens are seeded into the users table. |
| Email and notifications | Out of scope. Watcher rows exist so this can be added without a schema migration. |
| Attachments (file blobs) | The schema records attachment metadata, but actual binary storage is not implemented. |
| Service Desk SLAs / queues | The `support-kanban` workflow approximates the spirit of Service Desk without the SLA engine. |
| Multi-tenant orgs | Single-tenant by design. |
| User groups | We use roles only. Could be added without changing tools. |
| Rich text in comments | Comments are plain text. The schema doesn't constrain this; the UI would need extra work to render ADF. |

## Realism dials

Everything below is tuned to make the env *feel* like an active company:

- **22 users** with realistic names spanning multiple functions.
- **9 sprints** distributed across projects with `started_at`/`completed_at`
  dates relative to "now" so the dashboard always looks current.
- **Hand-curated issues** for the headline epics + procedural filler.
- **Threaded comments** with realistic conversation patterns
  (acknowledge, ask, blocker, resolve).
- **Cross-project links** (`caused_by` from SUP to PLAT, `blocks`
  between SCRUM stories).
- **Custom fields** populated on appropriate issues (severity on bugs,
  root cause on resolved incidents, iteration on stories).
- **Stale work**: some issues have `updated_at` 20+ days ago so JQL
  queries like `updated <= -14d` always return results.

## Determinism

The seed builder is deterministic given the fixtures. `rebuild` from the
same `backend/app/seed/fixtures/*` + `backend/app/seed/content/*` produces
byte-identical `seed.db` files (modulo `created_at` timestamps, which we
anchor to a fixed epoch when seeding). This means scenario verifiers can
assert on exact issue IDs and counts.
