"""Pydantic request/response schemas used by the REST API and reused by MCP."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str
    display_name: Optional[str] = None
    avatar_color: str
    role: str


class UserMeOut(UserOut):
    api_token: str


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: Optional[str] = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    name: str
    description: Optional[str] = None
    project_type: str
    lead_id: Optional[str] = None
    workflow_id: str
    avatar_color: str
    next_issue_number: int


class ProjectCreateIn(BaseModel):
    key: str
    name: str
    description: Optional[str] = None
    workflow_id: str
    lead_id: Optional[str] = None
    project_type: str = "software"


class ProjectPatchIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    lead_id: Optional[str] = None
    default_assignee: Optional[str] = None
    avatar_color: Optional[str] = None


class WorkflowStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    category: str
    color: str
    board_list: str
    position: int
    is_initial: bool


class WorkflowTransitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    from_status_id: str
    to_status_id: str
    name: str


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: Optional[str] = None
    statuses: list[WorkflowStatusOut] = []
    transitions: list[WorkflowTransitionOut] = []


class AllowedTransitionOut(BaseModel):
    to_status_id: str
    to_status_name: str
    name: str


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    issue_id: str
    author_id: str
    body: str
    parent_comment_id: Optional[str] = None
    mentions: list[str] = []
    created_at: datetime
    edited_at: Optional[datetime] = None


class IssueLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_id: str
    target_id: str
    link_type: str
    created_at: datetime


class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_key: str
    issue_type: str
    summary: str
    description: Optional[str] = None
    status_id: str
    status: Optional[str] = None  # name, joined
    board_list: str
    priority: str
    owner: Optional[str] = None
    reporter: str
    parent_id: Optional[str] = None
    epic_id: Optional[str] = None
    story_points: Optional[int] = None
    resolution: Optional[str] = None
    due_date: Optional[date] = None
    labels: list[str] = []
    watchers: list[str] = []
    sprint_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class IssueDetailOut(IssueOut):
    """Extended view for issue detail page / MCP get_issue."""
    allowed_transitions: list[AllowedTransitionOut] = []
    outbound_links: list[IssueLinkOut] = []
    inbound_links: list[IssueLinkOut] = []
    recent_comments: list[CommentOut] = []
    sprint_name: Optional[str] = None


class IssueCreateIn(BaseModel):
    project_key: str
    issue_type: str = "Task"
    summary: str
    description: Optional[str] = None
    priority: str = "Medium"
    owner: Optional[str] = None
    story_points: Optional[int] = None
    labels: Optional[list[str]] = None
    parent_id: Optional[str] = None
    epic_id: Optional[str] = None


class IssuePatchIn(BaseModel):
    summary: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    story_points: Optional[int] = None
    due_date: Optional[date] = None
    parent_id: Optional[str] = None
    epic_id: Optional[str] = None
    resolution: Optional[str] = None
    reporter: Optional[str] = None
    issue_type: Optional[str] = None


class IssueSprintIn(BaseModel):
    sprint_id: Optional[str] = Field(
        None, description="Sprint to move the issue to, or null to remove it from any sprint."
    )


class IssueTransitionIn(BaseModel):
    to_status: str = Field(..., description="Target status name or id.")
    comment: Optional[str] = None


class IssueAssignIn(BaseModel):
    assignee: Optional[str] = Field(None, description="User id, or null to unassign.")


class IssueCommentIn(BaseModel):
    body: str
    parent_comment_id: Optional[str] = None


class IssueLinkIn(BaseModel):
    target: str
    link_type: str = "relates"


class IssueLabelIn(BaseModel):
    label: str


class SprintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_key: str
    name: str
    state: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    goal: Optional[str] = None


class SprintCreateIn(BaseModel):
    project_key: str
    name: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    goal: Optional[str] = None


class SprintAddIssuesIn(BaseModel):
    issue_ids: list[str]


class SprintCompleteIn(BaseModel):
    move_unfinished_to: Optional[str] = None


class BoardCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    issue: IssueOut


class BoardColumnOut(BaseModel):
    status_name: str
    board_list: str
    category: str
    color: str
    cards: list[BoardCardOut]


class BoardSnapshotOut(BaseModel):
    board_id: str
    project_key: str
    board_type: str
    active_sprint: Optional[SprintOut] = None
    columns: list[BoardColumnOut]


class SearchIn(BaseModel):
    jql: str
    limit: int = 50
    offset: int = 0


class SearchOut(BaseModel):
    jql: str
    total: int
    limit: int
    offset: int
    issues: list[IssueOut]


class SavedFilterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    owner_id: str
    jql: str
    description: Optional[str] = None
    shared: bool


class SavedFilterIn(BaseModel):
    name: str
    jql: str
    description: Optional[str] = None
    shared: bool = True


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    actor_id: str
    entity_type: str
    entity_id: str
    issue_id: Optional[str] = None
    action: str
    field: Optional[str] = None
    from_value: Optional[str] = None
    to_value: Optional[str] = None
    comment_body: Optional[str] = None
    created_at: datetime


class ProjectSummaryOut(BaseModel):
    project: ProjectOut
    total_issues: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    by_assignee: dict[str, int]
    active_sprint: Optional[SprintOut] = None
    active_sprint_progress: Optional[dict[str, int]] = None
    recent_activity: list[ActivityOut] = []


class LoginIn(BaseModel):
    api_token: str


class AdminResetOut(BaseModel):
    success: bool
    message: str


class BulkTransitionIn(BaseModel):
    jql: str
    to_status: str
    comment: Optional[str] = None


class BulkAssignIn(BaseModel):
    jql: str
    assignee: Optional[str] = None


class BulkResultOut(BaseModel):
    total_matched: int
    succeeded: int
    failed: list[dict[str, str]] = []
