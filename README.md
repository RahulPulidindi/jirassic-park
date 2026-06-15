# Jirassic Park

A high-fidelity Jira-like environment for humans *and* agents, running in a single Docker container. It ships with a browser UI, a REST API, and an MCP server — all three driving the same persistent state, plus a seeded "company" that feels lived-in from the first request.

## Three surfaces, one source of truth

The core design decision: the UI, API, and MCP are not three implementations of the same product — they're three doors into one. Every one of them calls the same Python service layer, so a change made by a human clicking the UI, a script hitting REST, or an agent calling a tool all land in the same place and show up everywhere.

- **Browser UI** at `/` — projects, boards, backlog, issue view, JQL search, settings, and admin.
- **REST API** at `/api/*` — every operation a human can do in the UI. It's also re-projected at `/rest/api/3/*` in Atlassian Cloud's wire shape, so an agent trained on real Jira works here with just a base-URL swap. See [docs/api.md](docs/api.md).
- **MCP server** at `/mcp/` — the same operations as `jira_*` tools, so an agent can do real work without touching a pixel. See [docs/mcp.md](docs/mcp.md).

All three delegate to `backend/app/services/`, backed by SQLite. There is exactly one place where state and history live, and the parity test suite asserts the surfaces can't drift apart.

## Ranger

Ranger (`tooling/parity/`) is an agent that runs in the background to keep two applications — real Jira and Jirassic Park — visually and behaviorally in sync. Rather than hand-replicating screens every time Jira shifts, Ranger watches for drift and proposes the fix:

- Playwright captures screenshots and behavioral traces from both applications across a set of screens and workflows.
- A multimodal model diffs them and reports concrete discrepancies; a coding agent then proposes a frontend-only patch.
- A pixel guardrail and a model judge gate every patch — regressions are reverted, improvements are kept, and the result is opened as a PR with before/after/target screenshots for review.

See [tooling/parity/README.md](tooling/parity/README.md).

## Quickstart

```bash
make build          # build the image (Node builds the UI -> Python serves it)
make run            # start the container on http://localhost:8080
make logs           # tail container logs
make reset          # restore state.db from the seed snapshot (instant rollback)
make seed           # rebuild the seed snapshot from fixtures (after schema changes)
make test           # run the test suite inside the container
make demo           # short REST walkthrough against the running container
make mcp-demo       # short MCP walkthrough
make agent-demo     # let Claude drive the MCP to complete a real workflow
make computer-use   # let a computer-use agent drive the UI through Firefox
make stop           # stop and remove the container
```

State lives in a Docker volume at `/data` holding two SQLite files: `seed.db` (an immutable golden snapshot built at image-build time) and `state.db` (the working DB everything mutates). It persists across restarts; `make reset` is just a file copy of `seed.db` → `state.db`, so rollback is instant and total.

## What's in the seed

The goal was a workspace that feels like an active company, not an empty CRUD demo:

- **22 users** with realistic names, roles, and API tokens.
- **4 projects** — `SCRUM` (Customer App), `PLAT` (Platform), `DEBT` (Tech Debt), all scrum; `SUP` (Support), kanban.
- **2 workflows** with full state machines and named transitions.
- **9 sprints** spanning closed, active, and future, with dates relative to a controllable clock.
- **4 boards** (one per project) and **12 saved JQL filters** ("Open support tickets", "Bugs assigned to me", …).
- **~400 issues** — hand-curated ones with threaded comments, cross-project links, watchers, and labels, padded with procedurally-generated filler so search and boards have weight.
- **Custom fields** (`severity`, `root_cause`, `iteration`) and **synthesized audit history** for every issue, so activity feeds look real from the start.

## Example workflows

Auth is `Authorization: Bearer <api_token>`; the UI login screen takes the same tokens. Seeded tokens include `admin-token-jurassic` (global admin), `token_sarah_kim` (SCRUM lead), and `token_marcus_obrien` (PLAT lead) — full list in `backend/app/seed/fixtures/users.yaml`.

### UI

Visit `http://localhost:8080`, log in with any seeded token, and explore: `/projects`, `/board?key=PLAT`, `/backlog?key=SCRUM`, `/issue?id=PLAT-12`, `/search`, `/settings?key=SCRUM`, `/admin/users`.

### REST

```bash
# Project summary
curl -H "Authorization: Bearer admin-token-jurassic" \
     http://localhost:8080/api/projects/SCRUM/summary

# Create a bug
curl -X POST http://localhost:8080/api/issues \
     -H "Authorization: Bearer token_marcus_obrien" \
     -H "Content-Type: application/json" \
     -d '{"project_key":"PLAT","issue_type":"Bug","summary":"Login flakes",
          "description":"Race in the session middleware."}'

# Transition an issue
curl -X POST http://localhost:8080/api/issues/PLAT-12/transitions \
     -H "Authorization: Bearer token_marcus_obrien" \
     -H "Content-Type: application/json" \
     -d '{"to_status":"In Progress"}'

# JQL search
curl -H "Authorization: Bearer admin-token-jurassic" \
     'http://localhost:8080/api/search?jql=project%20%3D%20PLAT%20AND%20status%20%3D%20%22In%20Progress%22'
```

Full reference + the `/rest/api/3/*` Atlassian-compatible projection: [docs/api.md](docs/api.md).

### MCP

The MCP server is mounted at `/mcp/` over the standard MCP HTTP transport. Tools authenticate via the `auth_token` argument or the `Authorization` header.

```python
# In-process example (used by tests). The agent demo uses streamable-HTTP.
from mcp.server.fastmcp import FastMCP
from app.mcp.tools_impl import register

m = FastMCP("demo"); register(m)

await m.call_tool("jira_get_issue",        {"auth_token": "admin-token-jurassic", "id": "PLAT-12"})
await m.call_tool("jira_search_issues",    {"auth_token": "admin-token-jurassic",
                                            "jql": "project=PLAT and status=Done"})
await m.call_tool("jira_create_issue",     {"auth_token": "token_marcus_obrien",
                                            "project_key": "PLAT", "issue_type": "Bug",
                                            "summary": "Login flakes"})
await m.call_tool("jira_transition_issue", {"auth_token": "token_marcus_obrien",
                                            "id": "PLAT-12", "to_status": "In Progress"})
```

A typical multi-step agent task ("escalate SUP-1 to engineering") looks like:

```
jira_get_issue(id="SUP-1")
jira_get_project(project_key="PLAT")
jira_create_issue(project_key="PLAT", issue_type="Bug", summary=..., description=...)
jira_link_issues(from_id="SUP-1", to_id="PLAT-XX", link_type="relates")
jira_assign_issue(id="PLAT-XX", assignee="user_marcus_obrien")
jira_add_comment(id="SUP-1", body="Escalated to engineering as PLAT-XX.")
```

Full tool catalog + per-tool argument schemas: [docs/mcp.md](docs/mcp.md).

### Agent demos

- `make agent-demo` points Claude at `/mcp/` and lets it complete the SUP→PLAT escalation above with no further instructions. Its reasoning and every tool call stream to stdout.
- `make computer-use` runs Anthropic's reference computer-use agent in a sibling container; its Firefox drives the same UI a human would. Pick a task: `ops/computer-use-task.md` (full escalation) or `ops/computer-use-task-create-issue.md` (just create one issue).

Both demos need `ANTHROPIC_API_KEY` exported.

## Verification

```bash
make test                                    # full suite, inside the container
pytest backend/tests/test_surface_parity.py  # proves UI/REST/MCP can't drift
pytest backend/tests/test_jira_compat.py     # proves /rest/api/3 matches real Jira's wire shape
```

100+ tests across nine suites. The two called out above carry the "one source of truth" claim: `test_surface_parity.py` runs every paired operation through both REST and MCP and asserts the resulting `issues`, `activities`, `comments`, `watchers`, `issue_labels`, `issue_links`, `sprints`, and `saved_filters` rows come out identical. Walkthrough: [docs/scenarios/05-surface-parity.md](docs/scenarios/05-surface-parity.md).

## Architecture (short)

Full doc: [docs/architecture.md](docs/architecture.md).

- **Data model** — SQLAlchemy ORM over SQLite. Core tables: `users`, `projects`, `issues`, `comments`, `activities` (audit log), `issue_links`, `issue_labels`, `watchers`, `sprints`, `boards`, `saved_filters`, `workflows`, `statuses`, `transitions`. Every mutation writes an `activities` row in the same transaction, so history is a byproduct of doing work, not a separate code path.
- **Workflow / state machine** — statuses and named transitions live in `workflows.yaml`; the service layer enforces legal next-states and guards (epics can't close with open children, support tickets need a resolution before "Closed"). Illegal transitions return `422` with the allowed next statuses in the error body.
- **Search** — a "JQL-lite" parser (`app/services/jql.py`) covering the fields, operators, and functions agents actually reach for (`=`, `!=`, `IN`, `IS EMPTY`, `>`, `<`, `currentUser()`, `unassigned()`, relative dates like `-7d`). Same evaluator behind the UI, REST, and MCP.
- **Permissions** — three project roles (`lead`, `member`, `viewer`) plus global `admin`. Reads are open to any authenticated user; mutations require membership, reporter/assignee, or admin; lead-only ops cover settings, sprints, and filter ownership.
- **Persistence** — `seed.db` (immutable golden) and `state.db` (working DB) in the `/data` volume; schema versioned via `PRAGMA user_version`, with the entrypoint rebuilding from fixtures if the on-disk DB drifts from the code.
- **Universal clock** — every timestamp flows through `app.clock.now()`. Freeze it (`JP_CLOCK=frozen:<iso>`) for byte-identical replays, or advance it at runtime (`POST /api/admin/clock`) to exercise SLA and due-date behavior.

**Known gaps from real Jira:** single tenant (no orgs/sites), no custom-field schema editor, no per-screen field configs, no automation rules, no attachment bytes (metadata only), and notifications land in the in-app feed rather than email/Slack.

## Fidelity (short)

Full doc: [docs/fidelity.md](docs/fidelity.md).

**Modeled closely:**

- Issue-key scheme (`PROJ-N`), per-project counters, immutable keys.
- Workflow guards — epic-with-open-children, kanban "Resolved" before "Closed", named transitions per status pair.
- Activity-log granularity — every field change records actor, before, after, and timestamp.
- JQL operator surface, including the null-sentinel forms (`IS EMPTY`, `= EMPTY`, `unassigned()`).
- Atlassian wire shape on `/rest/api/3/*` — `accountId`s, `statusCategory`, ADF bodies, the `customfield_*` ids for story points / sprint / epic link, and `{errorMessages, errors}` errors.
- `data-testid` naming that mirrors Atlassian's (`ak-global-app-shell`, `issue.views.field.*`, …), so DOM and computer-use agents trained on real Jira find the same handles.

**Intentionally simplified (and why):**

- One workflow per project family rather than per issue type — the extra complexity rarely helps an agent learn.
- Two roles + admin instead of Jira's full permission scheme — the rest mostly matters to org admins.
- `@mentions` notify the in-app feed only; attachments store metadata, not bytes (keeps the seed reproducible in a few hundred MB).
- No automation rules — behavior stays predictable from the workflow and service layer alone.
- "JQL-lite" covers the common 80% of operators; extending it is mechanical when a task demands it.

## Repo layout

```
.
├── Dockerfile, Makefile, ops/entrypoint.sh
├── backend/
│   ├── app/
│   │   ├── api/         # FastAPI routers (thin shims over services)
│   │   ├── mcp/         # FastMCP server + jira_* tools
│   │   ├── services/    # all business logic (REST + MCP delegate here)
│   │   ├── models/      # SQLAlchemy ORM
│   │   ├── seed/        # YAML fixtures + seed builder
│   │   └── main.py
│   └── tests/
├── frontend/            # Next.js (static export, served by FastAPI)
├── tooling/parity/      # Ranger — background agent for UI/behavior parity with real Jira
└── docs/                # architecture, fidelity, api, mcp, scenarios
```

## Local development without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e backend
python -m app.seed.builder rebuild       # builds .data/state.db
DATA_DIR=$PWD/.data uvicorn app.main:app --reload --port 8080
# In another shell:
cd frontend && npm install && npm run dev
```

Or use `make dev-backend` / `make dev-frontend`.

## Further reading

- [docs/architecture.md](docs/architecture.md) — full architecture
- [docs/fidelity.md](docs/fidelity.md) — full fidelity rationale
- [docs/api.md](docs/api.md) — REST reference (both `/api` and `/rest/api/3`)
- [docs/mcp.md](docs/mcp.md) — MCP tool catalog
- [docs/scenarios/](docs/scenarios/) — five end-to-end scenarios with verifier predicates
