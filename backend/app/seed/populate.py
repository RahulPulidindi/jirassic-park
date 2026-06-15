"""Seed orchestrator. Reads YAML fixtures and content modules, populates the DB.

Deterministic: uses a fixed RNG seed so the same fixtures produce the same DB.
Idempotent: drops all data first, so calling rebuild repeatedly is safe.

Activities (audit log) are synthesized from the resulting state at the end:
- one `created` activity per issue
- one `transitioned` activity for issues whose current status is not the initial one
- one `assigned` activity per issue with an owner
- one `commented` activity per comment
- one `sprint_added` activity per sprint_issues row
- a `reopened` activity for any issue with `reopened: True`
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from app.db import session_scope
from app.models import (
    Activity,
    Board,
    Comment,
    CustomField,
    CustomFieldValue,
    Issue,
    IssueLabel,
    IssueLink,
    Label,
    Project,
    SavedFilter,
    Sprint,
    SprintIssue,
    Team,
    TeamMember,
    User,
    Watcher,
    Workflow,
    WorkflowStatus,
    WorkflowTransition,
)

# Deterministic seed - changing this changes generated assignees, ranks, etc.
RNG_SEED = 4242

# Project lead used as default reporter when an issue doesn't specify one.
PROJECT_DEFAULT_REPORTERS = {
    "SCRUM": "user_sarah_kim",
    "PLAT": "user_raj_patel",
    "DEBT": "user_maya_chen",
    "SUP": "user_devon_lee",
}

# Per-project pool of likely assignees for filler issues.
PROJECT_TEAMS = {
    "SCRUM": [
        "user_sarah_kim",
        "user_priya_iyer",
        "user_jordan_smith",
        "user_camille_durand",
    ],
    "PLAT": [
        "user_raj_patel",
        "user_marcus_obrien",
        "user_lina_garcia",
        "user_aki_yamada",
        "user_noah_williams",
        "user_grace_okafor",
    ],
    "DEBT": [
        "user_maya_chen",
        "user_tomas_silva",
        "user_emma_rossi",
        "user_owen_walsh",
    ],
    "SUP": [
        "user_devon_lee",
        "user_dani_haddad",
        "user_yuki_tanaka",
    ],
}

ISSUE_TYPE_DEFAULTS = {
    "Story": {"sp_range": (3, 8)},
    "Task": {"sp_range": (1, 3)},
    "Bug": {"sp_range": (1, 5)},
    "Epic": {"sp_range": (13, 34)},
    "Subtask": {"sp_range": (1, 3)},
}


def populate() -> None:
    """Populate the database from fixtures + content modules."""
    # Anchor all relative timestamps in the seed to the universal clock so a
    # `JP_CLOCK=frozen:...` build is fully reproducible.
    from app.clock import now as _clock_now
    now = _clock_now().replace(microsecond=0)
    rng = random.Random(RNG_SEED)
    fixtures_dir = Path(__file__).parent / "fixtures"

    with session_scope() as db:
        _clear_all(db)
        _load_workflows(db, fixtures_dir, now)
        _load_users(db, fixtures_dir, now)
        _load_teams(db, fixtures_dir, now)
        _load_projects(db, fixtures_dir, now)
        _load_custom_fields(db, fixtures_dir)
        _load_labels(db, fixtures_dir)
        sprint_offsets = _load_sprints(db, fixtures_dir, now)
        _load_boards(db, fixtures_dir, now)
        issue_key_map = _load_all_issues(db, now, sprint_offsets, rng)
        _load_links(db, fixtures_dir, issue_key_map, now)
        _load_saved_filters(db, fixtures_dir, now)
        _synthesize_activities(db, now)


def _clear_all(db) -> None:
    """Truncate every table - safe because we always rebuild fully."""
    for table in [
        Activity, Watcher, IssueLink, IssueLabel, CustomFieldValue, Comment,
        SprintIssue, Issue, Sprint, Board, Label, SavedFilter,
        CustomField, Project, WorkflowTransition, WorkflowStatus, Workflow,
        TeamMember, Team, User,
    ]:
        db.query(table).delete()
    db.commit()


def _yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def _load_workflows(db, fixtures: Path, now: datetime) -> None:
    data = _yaml(fixtures / "workflows.yaml")
    for wf in data["workflows"]:
        db.add(Workflow(
            id=wf["id"], name=wf["name"], description=wf.get("description"),
            created_at=now,
        ))
        for s in wf["statuses"]:
            db.add(WorkflowStatus(
                id=s["id"], workflow_id=wf["id"], name=s["name"],
                category=s["category"], color=s["color"], board_list=s["board_list"],
                position=s["position"], is_initial=s.get("is_initial", False),
            ))
        db.flush()
        for i, t in enumerate(wf["transitions"]):
            db.add(WorkflowTransition(
                id=f"{wf['id']}_t_{i}", workflow_id=wf["id"],
                from_status_id=t["from"], to_status_id=t["to"], name=t["name"],
            ))
    db.flush()


def _load_users(db, fixtures: Path, now: datetime) -> None:
    data = _yaml(fixtures / "users.yaml")
    for u in data["users"]:
        db.add(User(
            id=u["id"], email=u["email"], name=u["name"],
            display_name=u.get("display_name"), avatar_color=u.get("avatar_color", "#5d6a99"),
            role=u.get("role", "member"), api_token=u["api_token"],
            created_at=now - timedelta(days=180), updated_at=now,
        ))
    db.flush()


def _load_teams(db, fixtures: Path, now: datetime) -> None:
    data = _yaml(fixtures / "teams.yaml")
    for t in data["teams"]:
        db.add(Team(id=t["id"], name=t["name"], description=t.get("description"),
                    created_at=now - timedelta(days=200), updated_at=now))
        for m in t["members"]:
            db.add(TeamMember(team_id=t["id"], user_id=m["user"], role=m.get("role", "member")))
    db.flush()


def _load_projects(db, fixtures: Path, now: datetime) -> None:
    data = _yaml(fixtures / "projects.yaml")
    for p in data["projects"]:
        db.add(Project(
            key=p["key"], name=p["name"], description=p.get("description"),
            project_type=p.get("project_type", "software"),
            lead_id=p.get("lead_id"), default_assignee=p.get("default_assignee"),
            workflow_id=p["workflow_id"], avatar_color=p.get("avatar_color", "#3d63d9"),
            next_issue_number=1,
            created_at=now - timedelta(days=180), updated_at=now,
        ))
    db.flush()


def _load_custom_fields(db, fixtures: Path) -> None:
    import json
    data = _yaml(fixtures / "custom_fields.yaml")
    for f in data["custom_fields"]:
        db.add(CustomField(
            id=f["id"], name=f["name"], field_type=f["field_type"],
            project_keys=json.dumps(f.get("project_keys", [])),
            options=json.dumps(f["options"]) if f.get("options") else None,
        ))
    db.flush()


def _load_labels(db, fixtures: Path) -> None:
    global _KNOWN_LABELS
    _KNOWN_LABELS = set()
    data = _yaml(fixtures / "labels.yaml")
    for name in data["labels"]:
        db.add(Label(name=name))
        _KNOWN_LABELS.add(name)
    db.flush()


def _load_sprints(db, fixtures: Path, now: datetime) -> dict:
    """Returns map sprint_id -> (start, end) for placing issue dates."""
    data = _yaml(fixtures / "sprints.yaml")
    sprint_dates: dict[str, tuple[datetime | None, datetime | None]] = {}
    for s in data["sprints"]:
        start = now + timedelta(days=s["start_offset_days"]) if "start_offset_days" in s else None
        end = now + timedelta(days=s["end_offset_days"]) if "end_offset_days" in s else None
        completed = (
            now + timedelta(days=s["completed_offset_days"]) if "completed_offset_days" in s else None
        )
        db.add(Sprint(
            id=s["id"], project_key=s["project_key"], name=s["name"],
            state=s["state"], start_date=start, end_date=end, completed_at=completed,
            goal=s.get("goal"), created_at=(start or now) - timedelta(days=3),
        ))
        sprint_dates[s["id"]] = (start, end)
    db.flush()
    return sprint_dates


def _load_boards(db, fixtures: Path, now: datetime) -> None:
    data = _yaml(fixtures / "boards.yaml")
    for b in data["boards"]:
        db.add(Board(
            id=b["id"], project_key=b["project_key"], name=b["name"],
            board_type=b["board_type"], filter_jql=b.get("filter_jql"),
            created_at=now - timedelta(days=120),
        ))
    db.flush()


_KNOWN_LABELS: set[str] = set()


def _ensure_label(db, name: str) -> None:
    if name in _KNOWN_LABELS:
        return
    existing = db.query(Label).filter(Label.name == name).one_or_none()
    if existing is None:
        db.add(Label(name=name))
        db.flush()
    _KNOWN_LABELS.add(name)


def _resolve_status_id(db, workflow_id: str, status_name: str) -> str:
    s = (
        db.query(WorkflowStatus)
        .filter(WorkflowStatus.workflow_id == workflow_id, WorkflowStatus.name == status_name)
        .one_or_none()
    )
    if s is None:
        raise ValueError(f"Unknown status '{status_name}' in workflow {workflow_id}")
    return s.id


def _resolve_board_list(db, status_id: str) -> str:
    s = db.query(WorkflowStatus).filter(WorkflowStatus.id == status_id).one()
    return s.board_list


def _load_all_issues(db, now: datetime, sprint_dates: dict, rng: random.Random) -> dict[str, dict[int, str]]:
    """Load issues for every project; return {(project_key, id_hint) -> issue_id} for link resolution."""
    from app.seed.content import (
        debt_issues, plat_issues, scrum_issues, sup_issues,
    )
    from app.seed.content.comment_threads import THREADS

    # Initial status name per workflow (the workflow's `is_initial=True` status)
    workflows = {w.id: w for w in db.query(Workflow).all()}
    initial_status_per_workflow: dict[str, WorkflowStatus] = {}
    for w in workflows.values():
        initial = next((s for s in w.statuses if s.is_initial), w.statuses[0])
        initial_status_per_workflow[w.id] = initial

    projects = {p.key: p for p in db.query(Project).all()}
    project_data = {
        "SCRUM": (scrum_issues.ISSUES, scrum_issues.FILLER),
        "PLAT": (plat_issues.ISSUES, plat_issues.FILLER),
        "DEBT": (debt_issues.ISSUES, debt_issues.FILLER),
        "SUP": (sup_issues.ISSUES, sup_issues.FILLER),
    }

    # Map (project_key, id_hint) -> actual issue id
    id_map: dict[str, dict[int, str]] = {pk: {} for pk in projects}

    # For tracking subtask/epic linking - resolve after issues exist
    deferred_parent_links: list[tuple[str, int, int]] = []  # (project_key, child_id_hint, parent_id_hint)

    for project_key, project in projects.items():
        hand_curated, filler = project_data[project_key]
        wf = workflows[project.workflow_id]
        initial_status = initial_status_per_workflow[project.workflow_id]
        team_pool = PROJECT_TEAMS[project_key]
        default_reporter = PROJECT_DEFAULT_REPORTERS[project_key]
        n = 1

        # ---- Hand-curated issues ----
        for spec in hand_curated:
            issue_id = f"{project_key}-{n}"
            id_hint = spec.get("id_hint")
            if id_hint is not None:
                id_map[project_key][id_hint] = issue_id
            n += 1

            status_id = _resolve_status_id(db, project.workflow_id, spec.get("status", initial_status.name))
            board_list = _resolve_board_list(db, status_id)

            # Dates
            created = now + timedelta(days=spec.get("created_offset_days", -30))
            updated = now + timedelta(days=spec.get("updated_offset_days", -1))

            issue = Issue(
                id=issue_id, project_key=project_key,
                issue_type=spec.get("type", "Task"),
                summary=spec["summary"], description=spec.get("description"),
                status_id=status_id, board_list=board_list,
                priority=spec.get("priority", "Medium"),
                owner=spec.get("owner"),
                reporter=spec.get("reporter") or default_reporter,
                story_points=spec.get("story_points"),
                resolution=spec.get("resolution"),
                created_at=created, updated_at=updated,
            )
            db.add(issue)
            db.flush()

            # Labels (create label row if not yet seen)
            for lbl in spec.get("labels", []):
                _ensure_label(db, lbl)
                db.add(IssueLabel(issue_id=issue_id, label_name=lbl))

            # Watchers
            for w_id in spec.get("watchers", []):
                db.add(Watcher(issue_id=issue_id, user_id=w_id, created_at=created + timedelta(hours=1)))

            # Comments
            base_ts = created + timedelta(hours=2)
            for i, c in enumerate(spec.get("comments", [])):
                db.add(Comment(
                    id=f"comment_{issue_id}_{i}", issue_id=issue_id,
                    author_id=c["author"], body=c["body"],
                    created_at=base_ts + timedelta(hours=i * 6),
                ))

            # Sprint membership
            if spec.get("sprint"):
                db.add(SprintIssue(
                    sprint_id=spec["sprint"], issue_id=issue_id,
                    rank=f"0|{n:06d}",
                    added_at=created,
                ))

            # Subtask/epic deferred linking
            if spec.get("parent"):
                deferred_parent_links.append((project_key, id_hint, spec["parent"]))
            if spec.get("epic"):
                # epic field is also an id_hint into the same project's issues
                deferred_parent_links.append((project_key, id_hint, ("epic", spec["epic"])))

            # Custom fields
            import json as _json
            for cf_id, val in spec.get("custom_fields", {}).items():
                db.add(CustomFieldValue(
                    issue_id=issue_id, custom_field_id=cf_id,
                    value=_json.dumps(val),
                ))

        # ---- Filler issues ----
        # We spread creation across the past ~180 days with realistic clustering.
        for type_, summary, status, priority, labels in filler:
            issue_id = f"{project_key}-{n}"
            n += 1

            status_id = _resolve_status_id(db, project.workflow_id, status)
            board_list = _resolve_board_list(db, status_id)

            # Older if Done/Closed, recent if In Progress, scattered if Backlog/Open
            if status in ("Done", "Closed", "Resolved"):
                days_old = rng.randint(45, 170)
                updated_days = rng.randint(days_old - 30, days_old - 1)
            elif status in ("In Progress", "Working", "In Review"):
                days_old = rng.randint(5, 35)
                updated_days = rng.randint(0, 5)
            else:
                days_old = rng.randint(15, 160)
                updated_days = rng.randint(0, min(days_old - 1, 90))

            created = now - timedelta(days=days_old, hours=rng.randint(0, 23))
            updated = now - timedelta(days=updated_days, hours=rng.randint(0, 23))

            sp_lo, sp_hi = ISSUE_TYPE_DEFAULTS[type_]["sp_range"]
            story_points = rng.choice([None, rng.randint(sp_lo, sp_hi), rng.randint(sp_lo, sp_hi)])

            # ~15% of filler issues are unassigned
            owner = None if rng.random() < 0.15 else rng.choice(team_pool)
            reporter = rng.choice([default_reporter] + team_pool)

            resolution = None
            if status in ("Done", "Closed", "Resolved"):
                resolution = rng.choice(["Fixed", "Fixed", "Fixed", "Duplicate", "Won't Fix"])

            db.add(Issue(
                id=issue_id, project_key=project_key,
                issue_type=type_, summary=summary,
                status_id=status_id, board_list=board_list,
                priority=priority, owner=owner, reporter=reporter,
                story_points=story_points, resolution=resolution,
                created_at=created, updated_at=updated,
            ))
            db.flush()

            for lbl in labels:
                _ensure_label(db, lbl)
                db.add(IssueLabel(issue_id=issue_id, label_name=lbl))

            # Threaded comments on ~40% of filler issues
            if rng.random() < 0.40:
                thread = rng.choice(THREADS)
                for i, (author, body) in enumerate(thread):
                    db.add(Comment(
                        id=f"comment_{issue_id}_{i}", issue_id=issue_id,
                        author_id=author, body=body,
                        created_at=created + timedelta(days=rng.randint(0, 3), hours=i * 4),
                    ))

            # ~20% of filler get an extra watcher
            if rng.random() < 0.20 and owner:
                pool_minus_owner = [u for u in team_pool if u != owner]
                if pool_minus_owner:
                    db.add(Watcher(
                        issue_id=issue_id, user_id=rng.choice(pool_minus_owner),
                        created_at=created + timedelta(hours=2),
                    ))

        # Update project counter (next issue starts here)
        project.next_issue_number = n

    db.flush()

    # ---- Resolve deferred parent/epic links ----
    for project_key, child_hint, target in deferred_parent_links:
        child_id = id_map[project_key].get(child_hint)
        if not child_id:
            continue
        if isinstance(target, tuple) and target[0] == "epic":
            epic_id = id_map[project_key].get(target[1])
            if epic_id:
                db.query(Issue).filter(Issue.id == child_id).update({"epic_id": epic_id})
        else:
            parent_id = id_map[project_key].get(target)
            if parent_id:
                db.query(Issue).filter(Issue.id == child_id).update({"parent_id": parent_id})
    db.flush()
    return id_map


def _load_links(db, fixtures: Path, id_map: dict, now: datetime) -> None:
    """Cross-project issue links."""
    import re

    data = _yaml(fixtures / "links.yaml")
    pat = re.compile(r"^([A-Z]+)-(\d+)$")
    for i, link in enumerate(data["links"]):
        m_src = pat.match(link["source"])
        m_tgt = pat.match(link["target"])
        if not (m_src and m_tgt):
            continue
        src_id = id_map.get(m_src.group(1), {}).get(int(m_src.group(2)))
        tgt_id = id_map.get(m_tgt.group(1), {}).get(int(m_tgt.group(2)))
        if not (src_id and tgt_id):
            continue
        db.add(IssueLink(
            id=f"link_{i}", source_id=src_id, target_id=tgt_id, link_type=link["link_type"],
            created_at=now - timedelta(days=10),
        ))


def _load_saved_filters(db, fixtures: Path, now: datetime) -> None:
    data = _yaml(fixtures / "saved_filters.yaml")
    for f in data["saved_filters"]:
        db.add(SavedFilter(
            id=f["id"], name=f["name"], owner_id=f["owner_id"],
            jql=f["jql"], description=f.get("description"),
            shared=f.get("shared", True), created_at=now - timedelta(days=90),
        ))


def _synthesize_activities(db, now: datetime) -> None:
    """Derive a believable activity log from the loaded state."""
    import uuid

    activity_id = 0

    def _add(actor_id, entity_type, entity_id, action, *, issue_id=None, field=None,
             from_value=None, to_value=None, comment_body=None, created_at=None):
        nonlocal activity_id
        activity_id += 1
        db.add(Activity(
            id=f"act_{activity_id:06d}_{uuid.uuid4().hex[:6]}",
            actor_id=actor_id, entity_type=entity_type, entity_id=entity_id,
            issue_id=issue_id, action=action, field=field,
            from_value=from_value, to_value=to_value, comment_body=comment_body,
            created_at=created_at or now,
        ))

    # All issues - created + (maybe) transitioned + assigned
    issues = db.query(Issue).all()
    statuses = {s.id: s for s in db.query(WorkflowStatus).all()}
    workflows = {w.id: w for w in db.query(Workflow).all()}
    initial_by_workflow = {
        w.id: next((s for s in w.statuses if s.is_initial), w.statuses[0])
        for w in workflows.values()
    }
    projects = {p.key: p for p in db.query(Project).all()}

    for issue in issues:
        proj = projects[issue.project_key]
        initial = initial_by_workflow[proj.workflow_id]

        _add(
            actor_id=issue.reporter, entity_type="issue", entity_id=issue.id,
            issue_id=issue.id, action="created",
            to_value=issue.summary, created_at=issue.created_at,
        )

        if issue.owner and issue.owner != issue.reporter:
            _add(
                actor_id=issue.reporter, entity_type="issue", entity_id=issue.id,
                issue_id=issue.id, action="assigned", field="owner",
                from_value=None, to_value=issue.owner,
                created_at=issue.created_at + timedelta(minutes=5),
            )

        if issue.status_id != initial.id:
            current = statuses[issue.status_id]
            _add(
                actor_id=issue.owner or issue.reporter, entity_type="issue", entity_id=issue.id,
                issue_id=issue.id, action="transitioned", field="status",
                from_value=initial.name, to_value=current.name,
                created_at=issue.updated_at,
            )

    # Comments - one activity each
    for c in db.query(Comment).all():
        _add(
            actor_id=c.author_id, entity_type="issue", entity_id=c.issue_id,
            issue_id=c.issue_id, action="commented", comment_body=c.body,
            created_at=c.created_at,
        )

    # Sprint memberships
    for si in db.query(SprintIssue).all():
        _add(
            actor_id="user_admin", entity_type="issue", entity_id=si.issue_id,
            issue_id=si.issue_id, action="sprint_added", field="sprint",
            to_value=si.sprint_id, created_at=si.added_at,
        )

    # Sprint lifecycle events
    for s in db.query(Sprint).all():
        if s.state == "active" and s.start_date:
            _add(
                actor_id=projects[s.project_key].lead_id or "user_admin",
                entity_type="sprint", entity_id=s.id, action="sprint_started",
                to_value=s.name, created_at=s.start_date,
            )
        if s.state == "closed" and s.completed_at:
            _add(
                actor_id=projects[s.project_key].lead_id or "user_admin",
                entity_type="sprint", entity_id=s.id, action="sprint_completed",
                to_value=s.name, created_at=s.completed_at,
            )

    # Links
    for ln in db.query(IssueLink).all():
        _add(
            actor_id="user_admin", entity_type="issue", entity_id=ln.source_id,
            issue_id=ln.source_id, action="linked", field="link",
            to_value=f"{ln.link_type}:{ln.target_id}", created_at=ln.created_at,
        )
