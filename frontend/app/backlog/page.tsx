"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { IssueCard } from "@/components/IssueCard";
import { api } from "@/lib/api";
import type { Issue, Sprint } from "@/lib/types";

export default function BacklogPage() {
  const params = useSearchParams();
  const projectKey = params.get("key") || "SCRUM";
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [sprintIssues, setSprintIssues] = useState<Record<string, Issue[]>>({});
  const [backlog, setBacklog] = useState<Issue[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busySprint, setBusySprint] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const allSprints = await api.sprints(projectKey);
    setSprints(allSprints);
    const issueMap: Record<string, Issue[]> = {};
    for (const s of allSprints) {
      if (s.state === "closed") continue;
      issueMap[s.id] = await api.sprintIssues(s.id);
    }
    setSprintIssues(issueMap);
    const r = await api.search(
      `project = "${projectKey}" AND sprint IS EMPTY AND status != Done`,
      200,
    );
    setBacklog(r.issues);
  }, [projectKey]);

  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, [refresh]);

  async function startSprint(s: Sprint) {
    setBusySprint(s.id);
    try {
      await api.startSprint(s.id);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusySprint(null);
    }
  }
  async function completeSprint(s: Sprint) {
    setBusySprint(s.id);
    try {
      const future = sprints.find((x) => x.state === "future");
      await api.completeSprint(s.id, future ? future.id : null);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusySprint(null);
    }
  }

  async function createSprint() {
    const name = window.prompt("Sprint name (e.g. 'Sprint 24')");
    if (!name) return;
    const goal = window.prompt("Sprint goal (optional)") || undefined;
    try {
      await api.createSprint({ project_key: projectKey, name: name.trim(), goal });
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <AppShell>
      <div className="px-6 py-4">
        <header className="mb-4 flex items-center justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-ink-500">
              {projectKey} · Backlog
            </div>
            <h1 className="text-xl font-semibold">Backlog</h1>
          </div>
          <button
            type="button"
            onClick={createSprint}
            className="rounded border border-ink-200 bg-white px-2.5 py-1 text-xs hover:bg-ink-100"
          >
            + Create sprint
          </button>
        </header>

        {error && (
          <div className="mb-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {sprints
          .filter((s) => s.state !== "closed")
          .map((s) => (
            <SprintSection
              key={s.id}
              sprint={s}
              issues={sprintIssues[s.id] || []}
              busy={busySprint === s.id}
              onStart={() => startSprint(s)}
              onComplete={() => completeSprint(s)}
            />
          ))}

        <div className="mt-4 rounded border border-ink-200 bg-white">
          <div className="flex items-center justify-between px-3 py-2 border-b border-ink-200 bg-ink-50">
            <h2 className="text-sm font-semibold">Backlog</h2>
            <span className="text-[11px] text-ink-500">
              {backlog.length} issue{backlog.length === 1 ? "" : "s"}
            </span>
          </div>
          <ul className="divide-y divide-ink-100">
            {backlog.length === 0 && (
              <li className="px-3 py-4 text-sm text-ink-400">Empty backlog.</li>
            )}
            {backlog.map((i) => (
              <li key={i.id} className="px-3 py-2">
                <IssueCard issue={i} draggable={false} compact />
              </li>
            ))}
          </ul>
        </div>
      </div>
    </AppShell>
  );
}

function SprintSection({
  sprint,
  issues,
  busy,
  onStart,
  onComplete,
}: {
  sprint: Sprint;
  issues: Issue[];
  busy: boolean;
  onStart: () => void;
  onComplete: () => void;
}) {
  const totalSp = issues.reduce((s, i) => s + (i.story_points || 0), 0);
  const isActive = sprint.state === "active";
  return (
    <div className="mt-4 rounded border border-ink-200 bg-white">
      <div className="flex items-center justify-between px-3 py-2 border-b border-ink-200 bg-ink-50">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold">{sprint.name}</h2>
            <span
              className={
                "rounded-sm px-1.5 py-0.5 text-[10px] uppercase tracking-wide " +
                (isActive
                  ? "bg-brand-500 text-white"
                  : sprint.state === "future"
                  ? "bg-ink-200 text-ink-700"
                  : "bg-green-100 text-green-800")
              }
            >
              {sprint.state}
            </span>
            <span className="text-[11px] text-ink-500">{issues.length} issues · {totalSp} SP</span>
          </div>
          {sprint.goal && <p className="text-xs text-ink-600 mt-0.5">{sprint.goal}</p>}
        </div>
        <div className="flex gap-2">
          {sprint.state === "future" && (
            <button
              type="button"
              className="rounded bg-brand-500 px-2.5 py-1 text-xs text-white hover:bg-brand-600 disabled:opacity-50"
              disabled={busy}
              onClick={onStart}
            >
              Start sprint
            </button>
          )}
          {sprint.state === "active" && (
            <button
              type="button"
              className="rounded border border-ink-200 px-2.5 py-1 text-xs hover:bg-ink-100 disabled:opacity-50"
              disabled={busy}
              onClick={onComplete}
            >
              Complete sprint
            </button>
          )}
        </div>
      </div>
      <ul className="divide-y divide-ink-100">
        {issues.length === 0 && (
          <li className="px-3 py-4 text-sm text-ink-400">No issues planned yet.</li>
        )}
        {issues.map((i) => (
          <li key={i.id} className="px-3 py-2">
            <IssueCard issue={i} draggable={false} compact />
          </li>
        ))}
      </ul>
    </div>
  );
}
