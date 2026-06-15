# Architecture

## One process, one DB, three surfaces

Jirassic Park runs in a single container, with a single Python process
(uvicorn → FastAPI) and a single SQLite file. The choice of "one process"
is deliberate:

- Reviewers should be able to `make run` and have everything up. No
  external Postgres, no Redis, no nginx.
- An immutable `seed.db` plus a mutable `state.db` makes "reset to a clean,
  realistic workspace" a file-copy operation.
- SQLite with `PRAGMA foreign_keys = ON` and `journal_mode = WAL` is fast
  enough for any agent or human-driven workload this env will see.

```
                  ┌──────────────────────────────────────────┐
   browser ─────► │ /              (Next.js static export)   │
                  │ /_next/static  (StaticFiles mount)       │
   curl    ─────► │ /api/*         (FastAPI routers)         │
   agent   ─────► │ /mcp           (FastMCP HTTP transport)  │
                  └──────────────────────────────────────────┘
                                     │
                                     ▼
                       ┌──────────────────────────┐
                       │   app.services.*         │
                       │   (issues, projects,     │
                       │    workflows, sprints,   │
                       │    boards, search,       │
                       │    permissions, history) │
                       └──────────────────────────┘
                                     │
                                     ▼
                       ┌──────────────────────────┐
                       │  SQLAlchemy / SQLite     │
                       │  /data/state.db          │
                       └──────────────────────────┘
```

## The "one source of truth" invariant

The single most important property of this codebase is:

> **REST handlers and MCP tools never mutate the database directly.** They
> always delegate to a function in `app.services.*`.

That function:

1. Validates input (Pydantic input dataclasses).
2. Enforces permissions (`app.services.permissions.require`).
3. Performs the state change against SQLAlchemy.
4. Writes audit rows (`app.services.history.*`).
5. Returns the freshly-mutated ORM object.

So the REST route for "transition an issue" is:

```python
@router.post("/{issue_id}/transitions")
def transition(issue_id, body, user=Depends(get_current_user), db=Depends(get_session)):
    issue = issues.transition_issue(db, user, issue_id, body.to_status, body.comment)
    return issue_to_detail(issue, db)
```

And the MCP tool is:

```python
@mcp.tool()
def jira_transition_issue(id: str, to_status: str, comment: str | None = None,
                          auth_token: str | None = None, ctx: Context = None):
    db, user = _resolve(auth_token, ctx)
    issue = issues.transition_issue(db, user, id, to_status, comment)
    return _dump(issue_to_detail(issue, db))
```

If both surfaces call the same function with the same inputs, both surfaces
produce the same DB state — by construction.

This is enforced by `tests/test_surface_parity.py`, which runs each
mutation through both surfaces in a fresh `state.db` and compares the
resulting rows column-by-column.

## Workflow engine

State transitions are not free-text. They're enforced by:

1. `workflow_statuses` — the nodes (e.g. `Backlog`, `In Progress`).
2. `workflow_transitions` — the edges, each named (`Submit for review`,
   `Approve`, ...).
3. Guards in `app.services.workflows.evaluate_guards`, currently:
   - Epics cannot move to `Done` while any child is unresolved.
   - Stories cannot move to `Done` while any sub-task is unresolved.
   - (Easy to add more — e.g. "must have an assignee before
     In Progress", "must have story points before sprint commit".)

`Issue.board_list` is updated atomically with `status_id` on every
transition; the board view reads `board_list` directly, so columns never
drift from statuses.

## JQL-lite

`app.services.search` implements a small, faithful subset of JQL:

- Tokens: identifiers (alnum + `_ . -`), numbers, strings (single/double
  quoted), comparison operators (`=`, `!=`, `<`, `>`, `<=`, `>=`, `~`,
  `!~`, `in`, `not in`), boolean keywords (`AND`, `OR`, `NOT`), parens,
  `ORDER BY`.
- Functions: `currentUser()`, `unassigned()`, `now()`.
- Relative dates: `-7d`, `-2w`, `-3m`, `-1y`.
- Cross-table joins for `labels`, `sprint`, and `text` (full-text on
  id + summary + description + comments — so `text ~ "PLAT-60"` is a hit
  on PLAT-60 itself, mirroring Jira's quick-search semantics).
- Saved filter expansion: `filter = "name"` inlines the filter's JQL into
  the AST before evaluation.

The parser builds an AST (`QueryNode`, `BoolNode`, `Comparison`, `Func`,
`InList`); the evaluator translates the AST to SQLAlchemy expressions.
Adding a new field is a matter of a one-line mapping in
`_FIELDS_TO_COLUMN` + (optionally) a join in `Evaluator._joins`.

## Permissions (RBAC)

There are two levels:

- **Global role** on `User.role`: `admin`, `member`, `viewer`. Admins
  bypass all checks. Viewers cannot mutate.
- **Per-project role** on `Project.lead` + project membership:
  - `lead` — can manage sprints, change project settings.
  - `developer` / `reporter` — standard mutation.
  - `viewer` — read-only.

`app.services.permissions.require(action, user, project=None, issue=None)`
is the only gate; both surfaces hit it.

## Static UI

The frontend is a Next.js app exported to plain HTML/JS
(`next.config.mjs: output: "export"`). It's built in a Node stage of the
Dockerfile and copied to `/app/static/` in the Python stage. FastAPI
serves it via:

- `StaticFiles` mounted at `/_next/static` (the JS/CSS assets).
- A small SPA fallback route on `/` that serves `index.html` for unknown
  paths, but ignores `/api/*` and `/mcp`, so client-side routes work and
  API routes still 404 cleanly when missing.

Because everything is static, the UI works behind any HTTP server, can be
served from S3, etc.

## What's not here (on purpose)

- No external auth (OAuth/SAML). Tokens are static bearer tokens in the
  users table. Easy to swap.
- No email or notifications.
- No file storage for attachments (the schema is present so REST/MCP
  tools can record them, but no blob store).
- No Postgres / message queue / cache.
