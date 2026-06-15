# REST API Reference

Jirassic Park exposes **two REST surfaces** over the same underlying service
layer:

| Prefix          | Audience                                       | Response shape                                                |
| --------------- | ---------------------------------------------- | ------------------------------------------------------------- |
| `/api/*`        | Internal: this app's React UI                  | Compact `IssueOut`, `{detail: "..."}` errors                  |
| `/rest/api/3/*` | External: tool-using agents trained on Jira    | Atlassian REST v3 shape (`{id, key, self, fields: {...}}`), `{errorMessages, errors}` envelope, `startAt/maxResults/total` pagination, ADF for rich text |

The `/rest/api/3/*` surface is the **tool-agent compatibility layer**. Its
endpoint URLs, JSON keys, customfield ids (story points = `customfield_10016`,
sprint = `customfield_10020`, epic link = `customfield_10014`, flagged =
`customfield_10019`), `accountId` / `statusCategory` / `priority` shapes, and
error envelope all mirror Atlassian's published REST v3 contract. An agent
that learned to call Atlassian Cloud directly can drop into Jirassic Park by
swapping the base URL — no request/response handler changes required.

See [Jira-compat reference](#jira-rest-v3-compatibility-surface) for the full
endpoint list.

All endpoints below are mounted under `/api`. Authentication is required for
everything except `/api/auth/login` and `/health`.

### Authentication

Pass `Authorization: Bearer <api_token>` on every request. Tokens are stored
on the `users` table. For local development the UI also sets a `jp_token`
cookie (same value).

The OpenAPI schema is always available at `GET /api/openapi.json` and a
Swagger UI is hosted at `GET /api/docs` while the container is running. The
table below is a fast index.

### Demo bearer tokens

| Token                          | User                 | Role / Notes              |
| ------------------------------ | -------------------- | ------------------------- |
| `admin-token-jurassic`         | `user_admin`         | Global admin              |
| `token_sarah_kim`              | `user_sarah_kim`     | SCRUM lead (PM)           |
| `token_marcus_obrien`          | `user_marcus_obrien` | PLAT lead                 |
| `token_priya_iyer`             | `user_priya_iyer`    | Senior eng, SCRUM         |
| `token_lina_garcia`            | `user_lina_garcia`   | PLAT engineer             |
| `token_devon_lee`              | `user_devon_lee`     | SUP lead, on-call         |
| `token_observer`               | `user_observer`      | Read-only viewer          |

The full token list lives in `backend/app/seed/fixtures/users.yaml`.

---

## Endpoints

### Auth

| Method | Path               | Purpose                                        |
| ------ | ------------------ | ---------------------------------------------- |
| POST   | `/auth/login`      | Exchange `{api_token}` for cookie + user info  |
| POST   | `/auth/logout`     | Clear cookie                                   |
| GET    | `/auth/me`         | Current user                                   |

### Projects

| Method | Path                              | Purpose                                          |
| ------ | --------------------------------- | ------------------------------------------------ |
| GET    | `/projects`                       | List visible projects                            |
| GET    | `/projects/{key}`                 | Project details                                  |
| POST   | `/projects`                       | Create (admin only)                              |
| PATCH  | `/projects/{key}`                 | Update (lead/admin)                              |
| GET    | `/projects/{key}/workflow`        | Workflow with statuses + transitions             |
| GET    | `/projects/{key}/summary`         | Counts by status, sprint progress, top assignees |

### Users

| Method | Path                       | Purpose                                                                       |
| ------ | -------------------------- | ----------------------------------------------------------------------------- |
| GET    | `/users`                   | List all users                                                                |
| GET    | `/users/{id}`              | One user                                                                      |
| GET    | `/users/me/mentions`       | Recent `@`-mentions of the current user (newest first). Sources: comment bodies AND issue descriptions. Editing a description only fires notifications for *new* recipients. Query: `limit`, `since` (ISO). |

### Issues

| Method | Path                                | Purpose                                          |
| ------ | ----------------------------------- | ------------------------------------------------ |
| GET    | `/issues/{id}`                      | Issue with comments + history + links + watchers |
| POST   | `/issues`                           | Create                                           |
| PATCH  | `/issues/{id}`                      | Partial update. Editable fields: `summary`, `description`, `priority`, `story_points`, `due_date`, `parent_id`, `epic_id`, `resolution`, `reporter`, `issue_type`. |
| POST   | `/issues/{id}/transitions`         | Apply named transition (`{to_status, comment?}`) |
| POST   | `/issues/{id}/assign`              | Assign / unassign (`{assignee}` or `{assignee: null}`) |
| PUT    | `/issues/{id}/sprint`              | Move to sprint (`{sprint_id}`) or to backlog (`{sprint_id: null}`) |
| GET    | `/issues/{id}/comments`            | List comments                                    |
| POST   | `/issues/{id}/comments`            | Add comment (`{body, parent_comment_id?}`)       |
| PATCH  | `/issues/{id}/comments/{cid}`      | Edit comment body (author or admin only). Sets `edited_at` and re-parses `@mentions`. |
| DELETE | `/issues/{id}/comments/{cid}`      | Delete comment (author or admin only). Emits a `comment_deleted` activity row that preserves the original body for audit. |
| POST   | `/issues/{id}/links`               | Add link (`{target, link_type}`)                 |
| DELETE | `/issues/{id}/links`               | Remove link (body: `{target, link_type}`)        |
| POST   | `/issues/{id}/labels`              | Add label (`{label}`)                            |
| DELETE | `/issues/{id}/labels/{label}`      | Remove label                                     |
| POST   | `/issues/{id}/watch`               | Watch                                            |
| DELETE | `/issues/{id}/watch`               | Unwatch                                          |
| GET    | `/issues/{id}/history`             | Activity history (newest first)                  |

### Search

| Method | Path                          | Purpose                                            |
| ------ | ----------------------------- | -------------------------------------------------- |
| GET    | `/search?jql=...`             | Run a JQL-lite query, returns `{total, issues}`    |
| POST   | `/search/bulk_transition`     | `{jql, to_status}` → transition every match        |
| POST   | `/search/bulk_assign`         | `{jql, assignee}` → reassign every match           |

JQL-lite supports Jira's null-sentinel forms: `<field> IS EMPTY`,
`<field> = EMPTY`, `<field> = NULL`, and the equivalent
`<field> IS NOT EMPTY`. Works on `assignee`, `reporter`, `sprint`, `epic`,
`parent`, `labels`, `due`, etc. Functions `unassigned()`, `empty()`,
`null()`, `currentUser()`, and `now()` are also recognized.

### Sprints

| Method | Path                                  | Purpose                                        |
| ------ | ------------------------------------- | ---------------------------------------------- |
| GET    | `/sprints?project_key=...&state=...`  | List sprints                                   |
| GET    | `/sprints/{id}`                       | One sprint                                     |
| GET    | `/sprints/{id}/issues`                | Issues currently in this sprint                |
| POST   | `/sprints`                            | Create sprint (lead/admin)                     |
| POST   | `/sprints/{id}/start`                 | future → active                                |
| POST   | `/sprints/{id}/complete`              | active → closed, with optional rollover target |
| POST   | `/sprints/{id}/issues`                | Add issues (`{issue_ids: [...]}`)              |
| DELETE | `/sprints/{id}/issues`                | Remove issues (`{issue_ids: [...]}`)           |

### Boards

| Method | Path                                       | Purpose                                  |
| ------ | ------------------------------------------ | ---------------------------------------- |
| GET    | `/boards`                                  | List boards                              |
| GET    | `/boards/{id}/snapshot?sprint_id=...`      | Column snapshot for board (scrum/kanban) |

### Saved filters

| Method | Path                          | Purpose                              |
| ------ | ----------------------------- | ------------------------------------ |
| GET    | `/filters`                    | Filters visible to current user      |
| GET    | `/filters/{id}`               | One filter                           |
| POST   | `/filters`                    | Create (`{name, jql, shared}`)       |

### Admin

| Method | Path                | Purpose                                                                                                                       |
| ------ | ------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| POST   | `/admin/reset`      | Copy `seed.db` → `state.db` (instant rollback). Admin only.                                                                   |
| POST   | `/admin/reseed`     | Rebuild `seed.db` from fixtures. Admin only.                                                                                  |
| POST   | `/admin/clock`      | Reconfigure the universal clock. Body: `{"mode":"frozen","at":"<iso>"} ∣ {"mode":"offset","seconds":N} ∣ {"mode":"advance","seconds":N} ∣ {"mode":"real"}`. Admin only. |

### Clock

| Method | Path          | Purpose                                                            |
| ------ | ------------- | ------------------------------------------------------------------ |
| GET    | `/clock`      | Read the env's universal clock state (mode, current `now`, etc.).  |

### Healthcheck

| Method | Path     | Purpose                          |
| ------ | -------- | -------------------------------- |
| GET    | `/health` (NOT under `/api`) | Always returns `{status: "ok"}` |

## Error format

Every non-2xx response is a single JSON object:

```json
{ "detail": "human-readable explanation" }
```

HTTP status codes:

- `400` — malformed input or invalid JQL
- `401` — missing or unknown bearer token
- `403` — authenticated but not permitted
- `404` — resource not found
- `409` — conflict (e.g. duplicate sprint name)
- `422` — workflow rejection (e.g. illegal transition or guard failure)

Transition errors deserve attention: they include the list of allowed next
statuses in the message, so a confused agent can recover.

```
422 Unprocessable Entity
{
  "detail": "Cannot transition from 'Backlog' to 'In Review'. Allowed next statuses: 'In Progress', 'To Do'."
}
```

---

## Jira REST v3 compatibility surface

Mounted at `/rest/api/3/*`. Same auth (`Authorization: Bearer <api_token>`),
same underlying service layer, Atlassian-shaped wire format.

### Issues

| Method | Path                                                | Notes                                                  |
| ------ | --------------------------------------------------- | ------------------------------------------------------ |
| GET    | `/rest/api/3/issue/{idOrKey}`                       | Accepts the human key (`PLAT-60`) or the numeric id.   |
| POST   | `/rest/api/3/issue`                                 | Body: `{fields: {project: {key}, issuetype: {name}, summary, ...}}`. |
| PUT    | `/rest/api/3/issue/{idOrKey}`                       | Patch a subset of fields. Returns 204.                 |
| PUT    | `/rest/api/3/issue/{idOrKey}/assignee`              | Body: `{accountId: "..."}` or `{accountId: null}`.     |
| GET    | `/rest/api/3/issue/{idOrKey}/transitions`           | Lists legal transitions for the issue's current state. |
| POST   | `/rest/api/3/issue/{idOrKey}/transitions`           | Body: `{transition: {id|name}, update?: {comment: [...]}}` |
| GET    | `/rest/api/3/issue/{idOrKey}/comment`               | Paginated: `startAt`, `maxResults`, `total`.           |
| POST   | `/rest/api/3/issue/{idOrKey}/comment`               | Body: `{body: <string or ADF>}`. Returns the comment.  |
| PUT    | `/rest/api/3/issue/{idOrKey}/comment/{commentId}`   | Author-or-admin only.                                  |
| DELETE | `/rest/api/3/issue/{idOrKey}/comment/{commentId}`   | Author-or-admin only.                                  |
| GET    | `/rest/api/3/issue/{idOrKey}/watchers`              | Includes `isWatching` for the caller.                  |
| POST   | `/rest/api/3/issue/{idOrKey}/watchers`              | Body: `"<accountId>"` or empty (watch self).           |
| DELETE | `/rest/api/3/issue/{idOrKey}/watchers?accountId=`   | Unwatch.                                               |
| GET    | `/rest/api/3/issue/{idOrKey}/changelog`             | Paginated history.                                     |

### Search

| Method | Path                       | Notes                                                          |
| ------ | -------------------------- | -------------------------------------------------------------- |
| GET    | `/rest/api/3/search`       | Query params: `jql`, `startAt`, `maxResults`, `fields`.        |
| POST   | `/rest/api/3/search`       | Body: `{jql, startAt, maxResults, fields}`.                    |

### Issue links

| Method | Path                                | Notes                                                                |
| ------ | ----------------------------------- | -------------------------------------------------------------------- |
| POST   | `/rest/api/3/issueLink`             | `{type: {name}, outwardIssue: {key}, inwardIssue: {key}}`.           |
| DELETE | `/rest/api/3/issueLink/{linkId}`    | Idempotent.                                                          |
| GET    | `/rest/api/3/issueLinkType`         | List known link types in Jira shape.                                 |

### Projects, users, metadata

| Method | Path                                | Notes                                            |
| ------ | ----------------------------------- | ------------------------------------------------ |
| GET    | `/rest/api/3/project`               | All projects.                                    |
| GET    | `/rest/api/3/project/{key}`         | Including lead, issuetypes.                      |
| GET    | `/rest/api/3/project/{key}/statuses`| Statuses grouped per issue type.                 |
| GET    | `/rest/api/3/myself`                | Current user as Atlassian user ref.              |
| GET    | `/rest/api/3/user?accountId=...`    | Single user lookup. Also accepts `username=`.    |
| GET    | `/rest/api/3/user/search?query=...` | Free-text user search.                           |
| GET    | `/rest/api/3/priority`              | Priorities (`1`–`5` = Highest..Lowest).          |
| GET    | `/rest/api/3/status`                | All workflow statuses with `statusCategory`.     |
| GET    | `/rest/api/3/issuetype`             | All issue types with `hierarchyLevel`.           |
| GET    | `/rest/api/3/field`                 | All known fields including the `customfield_*`s. |
| GET    | `/rest/api/3/serverInfo`            | Build metadata. Identifies as "jirassic-park".   |

### Error envelope (Jira-compat surface)

Real Jira returns errors as:

```json
4xx
{
  "errorMessages": ["Issue does not exist or you do not have permission to see it."],
  "errors": { "summary": "Summary is required." }
}
```

The handler is scoped to `/rest/api/3/*`. The legacy `/api/*` surface (used
by the React UI) keeps the original `{detail: "..."}` shape so the UI doesn't
have to learn two formats.
