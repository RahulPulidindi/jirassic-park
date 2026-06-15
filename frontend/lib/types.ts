// Shared TypeScript types matching the FastAPI Pydantic schemas (app/schemas/api.py).
// Kept hand-written to avoid an OpenAPI codegen step in the build.

export type Role = "admin" | "member" | "viewer";

export interface User {
  id: string;
  email: string;
  name: string;
  display_name: string | null;
  avatar_color: string;
  role: Role;
}

export interface UserMe extends User {
  api_token: string;
}

export interface Project {
  key: string;
  name: string;
  description: string | null;
  project_type: string;
  lead_id: string | null;
  workflow_id: string;
  avatar_color: string;
  next_issue_number: number;
}

export interface WorkflowStatus {
  id: string;
  name: string;
  category: "todo" | "in_progress" | "done";
  color: string;
  board_list: string;
  position: number;
  is_initial: boolean;
}

export interface WorkflowTransition {
  id: string;
  from_status_id: string;
  to_status_id: string;
  name: string;
}

export interface Workflow {
  id: string;
  name: string;
  description: string | null;
  statuses: WorkflowStatus[];
  transitions: WorkflowTransition[];
}

export interface AllowedTransition {
  to_status_id: string;
  to_status_name: string;
  name: string;
}

export interface Comment {
  id: string;
  issue_id: string;
  author_id: string;
  body: string;
  parent_comment_id: string | null;
  mentions: string[];
  created_at: string;
  edited_at: string | null;
}

export interface ClockState {
  mode: "real" | "frozen" | "tick" | "offset";
  now: string;
  wall_now: string;
  frozen_at: string | null;
  offset_seconds: number;
  tick_us: number | null;
}

export interface IssueLink {
  id: string;
  source_id: string;
  target_id: string;
  link_type: string;
  created_at: string;
}

export interface Issue {
  id: string;
  project_key: string;
  issue_type: string;
  summary: string;
  description: string | null;
  status_id: string;
  status: string | null;
  board_list: string;
  priority: string;
  owner: string | null;
  reporter: string;
  parent_id: string | null;
  epic_id: string | null;
  story_points: number | null;
  resolution: string | null;
  due_date: string | null;
  labels: string[];
  watchers: string[];
  sprint_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface IssueDetail extends Issue {
  allowed_transitions: AllowedTransition[];
  outbound_links: IssueLink[];
  inbound_links: IssueLink[];
  recent_comments: Comment[];
  sprint_name: string | null;
}

export interface Sprint {
  id: string;
  project_key: string;
  name: string;
  state: "future" | "active" | "closed";
  start_date: string | null;
  end_date: string | null;
  completed_at: string | null;
  goal: string | null;
}

export interface BoardCard {
  issue: Issue;
}

export interface BoardColumn {
  status_name: string;
  board_list: string;
  category: string;
  color: string;
  cards: BoardCard[];
}

export interface BoardSnapshot {
  board_id: string;
  project_key: string;
  board_type: string;
  active_sprint: Sprint | null;
  columns: BoardColumn[];
}

export interface SearchResponse {
  jql: string;
  total: number;
  limit: number;
  offset: number;
  issues: Issue[];
}

export interface SavedFilter {
  id: string;
  name: string;
  owner_id: string;
  jql: string;
  description: string | null;
  shared: boolean;
}

export interface Activity {
  id: string;
  actor_id: string;
  entity_type: string;
  entity_id: string;
  issue_id: string | null;
  action: string;
  field: string | null;
  from_value: string | null;
  to_value: string | null;
  comment_body: string | null;
  created_at: string;
}

export interface ProjectSummary {
  project: Project;
  total_issues: number;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  by_assignee: Record<string, number>;
  active_sprint: Sprint | null;
  active_sprint_progress: Record<string, number> | null;
  recent_activity: Activity[];
}
