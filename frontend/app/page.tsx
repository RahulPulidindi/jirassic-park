"use client";

import { Activity as ActivityIcon, ChevronRight, Folder, Star } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Avatar } from "@/components/Avatar";
import { IssueTypeIcon } from "@/components/IssueTypeIcon";
import { PriorityBadge } from "@/components/PriorityBadge";
import { api } from "@/lib/api";
import type { Activity, Issue, Project, ProjectSummary, SavedFilter, User } from "@/lib/types";
import { relativeTime } from "@/lib/utils";

export default function DashboardPage() {
  const [me, setMe] = useState<User | null>(null);
  const [myIssues, setMyIssues] = useState<Issue[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [filters, setFilters] = useState<SavedFilter[]>([]);
  const [recent, setRecent] = useState<Activity[]>([]);
  const [sprintProgress, setSprintProgress] = useState<ProjectSummary | null>(null);

  useEffect(() => {
    api.me().then(setMe).catch(() => {});
    api.projects().then(setProjects);
    api.filters().then(setFilters);
  }, []);

  useEffect(() => {
    if (!me) return;
    api
      .search('assignee = currentUser() AND status != "Done" ORDER BY priority DESC, updated DESC', 10)
      .then((r) => setMyIssues(r.issues));
    api.projectSummary("SCRUM").then(setSprintProgress).catch(() => {});
    api
      .search("updated >= -2d ORDER BY updated DESC", 20)
      .then((r) => {
        // Use search for activity-ish view; for full activity feed we'd extend the API
      });
  }, [me]);

  useEffect(() => {
    api
      .projectSummary("SCRUM")
      .then((s) => setRecent(s.recent_activity || []))
      .catch(() => {});
  }, []);

  return (
    <AppShell>
      <div className="px-8 py-6 max-w-7xl">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold">
            {me ? `Welcome back, ${me.display_name || me.name}` : "Dashboard"}
          </h1>
          <p className="text-ink-600 mt-1 text-sm">
            Your assigned work, active sprint progress, and starred filters.
          </p>
        </header>

        <div className="grid grid-cols-3 gap-6">
          <Card title="Assigned to me" hint={`${myIssues.length} open`}>
            {myIssues.length === 0 ? (
              <EmptyState>Nothing assigned to you. Enjoy the quiet.</EmptyState>
            ) : (
              <ul className="divide-y divide-ink-100">
                {myIssues.map((i) => (
                  <li key={i.id} className="py-2">
                    <Link
                      href={`/issue?id=${i.id}`}
                      className="flex items-center gap-2 hover:bg-ink-50 rounded -m-1 p-1"
                    >
                      <IssueTypeIcon type={i.issue_type} size={14} />
                      <span className="text-[12px] font-mono text-ink-500">{i.id}</span>
                      <span className="text-sm flex-1 truncate">{i.summary}</span>
                      <PriorityBadge priority={i.priority} size={14} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title="Active sprint - SCRUM"
            hint={sprintProgress?.active_sprint?.name || "no active sprint"}
            href="/board?key=SCRUM"
          >
            {sprintProgress?.active_sprint_progress ? (
              <ProgressBars data={sprintProgress.active_sprint_progress} />
            ) : (
              <EmptyState>No active sprint.</EmptyState>
            )}
          </Card>

          <Card title="Starred filters">
            <ul className="space-y-1">
              {filters.slice(0, 6).map((f) => (
                <li key={f.id}>
                  <Link
                    href={`/search?jql=${encodeURIComponent(f.jql)}&name=${encodeURIComponent(f.name)}`}
                    className="flex items-center gap-2 rounded p-1.5 hover:bg-ink-50 text-sm"
                  >
                    <Star size={14} className="text-amber-500" fill="currentColor" />
                    <span>{f.name}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Recent activity" hint="" className="col-span-2">
            <ul className="divide-y divide-ink-100 text-sm">
              {recent.slice(0, 12).map((a) => (
                <li key={a.id} className="py-2 flex items-center gap-2">
                  <ActivityIcon size={12} className="text-ink-400" />
                  <span className="font-mono text-[11px] text-ink-500">{a.issue_id}</span>
                  <span className="text-ink-700 flex-1 truncate">
                    {formatActivity(a)}
                  </span>
                  <span className="text-[11px] text-ink-400" title={a.created_at}>
                    {relativeTime(a.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Projects">
            <ul className="space-y-1">
              {projects.map((p) => (
                <li key={p.key}>
                  <Link
                    href={`/board?key=${p.key}`}
                    className="flex items-center gap-2 rounded p-1.5 hover:bg-ink-50 text-sm"
                  >
                    <span
                      className="inline-block h-3 w-3 rounded-sm"
                      style={{ backgroundColor: p.avatar_color }}
                    />
                    <span className="font-mono text-[11px] text-ink-500">{p.key}</span>
                    <span>{p.name}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}

function Card({
  title,
  hint,
  href,
  children,
  className,
}: {
  title: string;
  hint?: string;
  href?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={
        "rounded border border-ink-200 bg-white p-4 shadow-card " + (className || "")
      }
    >
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-baseline gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-700">
            {title}
          </h2>
          {hint && <span className="text-[11px] text-ink-500">{hint}</span>}
        </div>
        {href && (
          <Link href={href} className="text-[11px] text-brand-600 hover:underline flex items-center gap-0.5">
            View <ChevronRight size={12} />
          </Link>
        )}
      </div>
      {children}
    </div>
  );
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return <div className="text-sm text-ink-400 py-6 text-center">{children}</div>;
}

function ProgressBars({ data }: { data: Record<string, number> }) {
  const total = Object.values(data).reduce((s, n) => s + n, 0);
  if (total === 0) return <EmptyState>No issues in the active sprint.</EmptyState>;
  const order = ["todo", "in_progress", "done"];
  const labels: Record<string, string> = { todo: "To do", in_progress: "In progress", done: "Done" };
  const colors: Record<string, string> = {
    todo: "bg-ink-300",
    in_progress: "bg-brand-500",
    done: "bg-green-600",
  };
  return (
    <div>
      <div className="mb-2 flex h-2 w-full overflow-hidden rounded">
        {order.map((k) => (
          <div
            key={k}
            className={colors[k]}
            style={{ width: `${((data[k] || 0) / total) * 100}%` }}
            title={`${labels[k]}: ${data[k] || 0}`}
          />
        ))}
      </div>
      <div className="flex gap-3 text-[11px] text-ink-600">
        {order.map((k) => (
          <span key={k} className="flex items-center gap-1">
            <span className={`inline-block h-2 w-2 rounded-sm ${colors[k]}`} />
            {labels[k]}: <strong>{data[k] || 0}</strong>
          </span>
        ))}
      </div>
    </div>
  );
}

function formatActivity(a: Activity): string {
  if (a.action === "created") return `created${a.to_value ? `: "${a.to_value}"` : ""}`;
  if (a.action === "transitioned") return `${a.from_value} → ${a.to_value}`;
  if (a.action === "assigned")
    return a.to_value ? `assigned to ${a.to_value}` : "unassigned";
  if (a.action === "commented") return `commented`;
  if (a.action === "updated") return `${a.field}: ${a.from_value || "—"} → ${a.to_value || "—"}`;
  if (a.action === "sprint_added") return `added to sprint ${a.to_value}`;
  if (a.action === "linked") return `linked: ${a.to_value}`;
  if (a.action === "labeled") return `labeled: ${a.to_value}`;
  return a.action;
}
