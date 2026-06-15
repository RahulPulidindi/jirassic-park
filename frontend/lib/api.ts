"use client";

import type {
  Activity,
  BoardSnapshot,
  ClockState,
  Comment,
  Issue,
  IssueDetail,
  Project,
  ProjectSummary,
  SavedFilter,
  SearchResponse,
  Sprint,
  User,
  UserMe,
  Workflow,
} from "./types";

const API_BASE =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
    ? process.env.NEXT_PUBLIC_API_BASE
    : "";

const TOKEN_KEY = "jp_api_token";
const DEFAULT_DEMO_TOKEN = "token_sarah_kim";

export function getToken(): string {
  if (typeof window === "undefined") return DEFAULT_DEMO_TOKEN;
  return window.localStorage.getItem(TOKEN_KEY) || DEFAULT_DEMO_TOKEN;
}

export function setToken(token: string) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export function clearToken() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  detail: any;
  constructor(status: number, detail: any, msg: string) {
    super(msg);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  headers.set("Content-Type", "application/json");
  headers.set("Authorization", `Bearer ${getToken()}`);
  const resp = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: "include" });
  if (!resp.ok) {
    let detail: any = null;
    try {
      detail = await resp.json();
    } catch {
      /* ignore */
    }
    const msg = (detail && (detail.detail || detail.message)) || `${resp.status} ${resp.statusText}`;
    throw new ApiError(resp.status, detail, typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

// ------------------------- API surface -------------------------------

export const api = {
  // auth
  me: () => request<UserMe>("/api/auth/me"),
  login: (api_token: string) =>
    request<UserMe>("/api/auth/login", { method: "POST", body: JSON.stringify({ api_token }) }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),

  // users
  users: () => request<User[]>("/api/users"),
  user: (id: string) => request<User>(`/api/users/${id}`),
  myMentions: (limit = 50, since?: string) => {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (since) qs.set("since", since);
    return request<Activity[]>(`/api/users/me/mentions?${qs.toString()}`);
  },

  // clock
  clock: () => request<ClockState>("/api/clock"),

  // projects
  projects: () => request<Project[]>("/api/projects"),
  project: (key: string) => request<Project>(`/api/projects/${key}`),
  projectSummary: (key: string) => request<ProjectSummary>(`/api/projects/${key}/summary`),
  projectWorkflow: (key: string) => request<Workflow>(`/api/projects/${key}/workflow`),
  createProject: (body: {
    key: string;
    name: string;
    workflow_id: string;
    description?: string;
    lead_id?: string | null;
    project_type?: string;
  }) => request<Project>("/api/projects", { method: "POST", body: JSON.stringify(body) }),
  updateProject: (key: string, patch: Partial<Project> & { default_assignee?: string | null }) =>
    request<Project>(`/api/projects/${key}`, { method: "PATCH", body: JSON.stringify(patch) }),

  // issues
  issue: (id: string) => request<IssueDetail>(`/api/issues/${id}`),
  createIssue: (body: Partial<Issue>) =>
    request<IssueDetail>("/api/issues", { method: "POST", body: JSON.stringify(body) }),
  patchIssue: (id: string, patch: Record<string, any>) =>
    request<IssueDetail>(`/api/issues/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  transition: (id: string, to_status: string, comment?: string) =>
    request<IssueDetail>(`/api/issues/${id}/transitions`, {
      method: "POST",
      body: JSON.stringify({ to_status, comment }),
    }),
  assign: (id: string, assignee: string | null) =>
    request<IssueDetail>(`/api/issues/${id}/assign`, {
      method: "POST",
      body: JSON.stringify({ assignee }),
    }),
  setSprint: (id: string, sprint_id: string | null) =>
    request<IssueDetail>(`/api/issues/${id}/sprint`, {
      method: "PUT",
      body: JSON.stringify({ sprint_id }),
    }),
  comment: (id: string, body: string, parent_comment_id?: string) =>
    request<Comment>(`/api/issues/${id}/comments`, {
      method: "POST",
      body: JSON.stringify({ body, parent_comment_id }),
    }),
  comments: (id: string) => request<Comment[]>(`/api/issues/${id}/comments`),
  updateComment: (issueId: string, commentId: string, body: string) =>
    request<Comment>(`/api/issues/${issueId}/comments/${commentId}`, {
      method: "PATCH",
      body: JSON.stringify({ body }),
    }),
  deleteComment: (issueId: string, commentId: string) =>
    request<void>(`/api/issues/${issueId}/comments/${commentId}`, {
      method: "DELETE",
    }),
  history: (id: string) => request<Activity[]>(`/api/issues/${id}/history`),
  addLabel: (id: string, label: string) =>
    request<IssueDetail>(`/api/issues/${id}/labels`, {
      method: "POST",
      body: JSON.stringify({ label }),
    }),
  removeLabel: (id: string, label: string) =>
    request<IssueDetail>(`/api/issues/${id}/labels/${encodeURIComponent(label)}`, {
      method: "DELETE",
    }),
  watch: (id: string) => request<IssueDetail>(`/api/issues/${id}/watch`, { method: "POST" }),
  unwatch: (id: string) => request<IssueDetail>(`/api/issues/${id}/watch`, { method: "DELETE" }),
  linkIssue: (id: string, target: string, link_type: string) =>
    request<any>(`/api/issues/${id}/links`, {
      method: "POST",
      body: JSON.stringify({ target, link_type }),
    }),
  unlinkIssue: (id: string, target: string, link_type: string) =>
    request<void>(`/api/issues/${id}/links`, {
      method: "DELETE",
      body: JSON.stringify({ target, link_type }),
    }),

  // search
  search: (jql: string, limit = 50, offset = 0) =>
    request<SearchResponse>(
      `/api/search?jql=${encodeURIComponent(jql)}&limit=${limit}&offset=${offset}`,
    ),

  // sprints
  sprints: (project_key?: string) =>
    request<Sprint[]>(
      `/api/sprints${project_key ? `?project_key=${encodeURIComponent(project_key)}` : ""}`,
    ),
  sprint: (sprintId: string) => request<Sprint>(`/api/sprints/${sprintId}`),
  sprintIssues: (sprintId: string) => request<Issue[]>(`/api/sprints/${sprintId}/issues`),
  createSprint: (body: {
    project_key: string;
    name: string;
    start_date?: string | null;
    end_date?: string | null;
    goal?: string | null;
  }) => request<Sprint>("/api/sprints", { method: "POST", body: JSON.stringify(body) }),
  startSprint: (sprintId: string) =>
    request<Sprint>(`/api/sprints/${sprintId}/start`, { method: "POST" }),
  completeSprint: (sprintId: string, move_unfinished_to: string | null) =>
    request<Sprint>(`/api/sprints/${sprintId}/complete`, {
      method: "POST",
      body: JSON.stringify({ move_unfinished_to }),
    }),
  addToSprint: (sprintId: string, issue_ids: string[]) =>
    request<Sprint>(`/api/sprints/${sprintId}/issues`, {
      method: "POST",
      body: JSON.stringify({ issue_ids }),
    }),
  removeFromSprint: (sprintId: string, issue_ids: string[]) =>
    request<Sprint>(`/api/sprints/${sprintId}/issues`, {
      method: "DELETE",
      body: JSON.stringify({ issue_ids }),
    }),

  // boards
  boards: (project_key?: string) =>
    request<{ id: string; project_key: string; name: string; board_type: string }[]>(
      `/api/boards${project_key ? `?project_key=${encodeURIComponent(project_key)}` : ""}`,
    ),
  board: (boardId: string) => request<BoardSnapshot>(`/api/boards/${boardId}`),

  // filters
  filters: () => request<SavedFilter[]>("/api/filters"),
  filter: (id: string) => request<SavedFilter>(`/api/filters/${id}`),
  createFilter: (body: Partial<SavedFilter>) =>
    request<SavedFilter>("/api/filters", { method: "POST", body: JSON.stringify(body) }),

  // admin
  reset: () => request<{ success: boolean; message: string }>("/api/admin/reset", { method: "POST" }),
  reseed: () => request<{ success: boolean; message: string }>("/api/admin/reseed", { method: "POST" }),
  setClock: (body: { mode: string; at?: string; seconds?: number }) =>
    request<any>("/api/admin/clock", { method: "POST", body: JSON.stringify(body) }),
};
