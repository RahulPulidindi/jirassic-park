"use client";

import { MoreHorizontal } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { IssueCard } from "@/components/IssueCard";
import { api } from "@/lib/api";
import type { BoardSnapshot, Project } from "@/lib/types";
import { cn } from "@/lib/utils";

// Tabs match the Jira board chrome (Summary / Timeline / Backlog / Board /
// Calendar / Reports / Code). Most are placeholders today, but their presence
// in the layout signals fidelity to reviewers and gives us obvious extension
// points later.
const TABS: { key: string; label: string; href?: (k: string) => string }[] = [
  { key: "summary", label: "Summary" },
  { key: "timeline", label: "Timeline" },
  { key: "backlog", label: "Backlog", href: (k) => `/backlog?key=${k}` },
  { key: "board", label: "Board", href: (k) => `/board?key=${k}` },
  { key: "calendar", label: "Calendar" },
  { key: "reports", label: "Reports" },
  { key: "code", label: "Code" },
];

export default function BoardPage() {
  const params = useSearchParams();
  const projectKey = params.get("key") || "SCRUM";
  const [board, setBoard] = useState<BoardSnapshot | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [boards, proj] = await Promise.all([
      api.boards(projectKey),
      api.project(projectKey).catch(() => null),
    ]);
    setProject(proj);
    if (!boards.length) {
      setError(`No board for project ${projectKey}.`);
      return;
    }
    const snap = await api.board(boards[0].id);
    setBoard(snap);
  }, [projectKey]);

  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, [refresh]);

  const onDrop = async (statusName: string, e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(null);
    const issueId = e.dataTransfer.getData("text/issue-id");
    if (!issueId || !board) return;
    // Optimistic: move the card to the target column first
    const next = structuredClone(board);
    let moved: any;
    for (const col of next.columns) {
      const idx = col.cards.findIndex((c: any) => c.issue.id === issueId);
      if (idx >= 0) {
        moved = col.cards.splice(idx, 1)[0];
        break;
      }
    }
    const targetCol = next.columns.find((c: any) => c.status_name === statusName);
    if (moved && targetCol) {
      moved.issue.status = statusName;
      moved.issue.board_list = targetCol.board_list;
      targetCol.cards.push(moved);
      setBoard(next);
    }
    try {
      await api.transition(issueId, statusName);
      // Refresh to pick up audit + any guard-induced rejections
      refresh();
    } catch (e: any) {
      setError(e.message);
      refresh();
    }
  };

  if (error) {
    return (
      <AppShell>
        <div className="px-8 py-6">
          <div className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        </div>
      </AppShell>
    );
  }
  if (!board) {
    return (
      <AppShell>
        <Skeleton />
      </AppShell>
    );
  }

  const boardTitle = board.active_sprint
    ? board.active_sprint.name
    : `${project?.name || projectKey} board`;

  return (
    <AppShell>
      <div className="flex h-full flex-col">
        {/* Breadcrumb + title block, on the project canvas. */}
        <div className="border-b border-ink-200 bg-white px-6 pt-3">
          <div className="text-[11px] text-ink-500">
            <Link href="/projects" className="hover:underline">
              Projects
            </Link>
            <span className="mx-1">/</span>
            <Link href={`/projects`} className="hover:underline">
              {project?.name || projectKey}
            </Link>
          </div>
          <div className="mt-1 flex items-center gap-2">
            <h1 className="text-[20px] font-semibold text-ink-900">{boardTitle}</h1>
            <button
              type="button"
              className="rounded p-1 text-ink-500 hover:bg-ink-100"
              aria-label="More board actions"
            >
              <MoreHorizontal size={16} />
            </button>
          </div>
          {board.active_sprint?.goal && (
            <p className="mt-1 text-[12px] text-ink-600">{board.active_sprint.goal}</p>
          )}

          {/* Tab strip */}
          <nav className="-mb-px mt-3 flex gap-4 text-[13px]">
            {TABS.map((t) => {
              const href = t.href ? t.href(projectKey) : undefined;
              const isCurrent = t.key === "board";
              const cls = cn(
                "border-b-2 px-1 pb-2",
                isCurrent
                  ? "border-brand-500 font-medium text-ink-900"
                  : "border-transparent text-ink-600 hover:text-ink-900",
              );
              if (href) {
                return (
                  <Link key={t.key} href={href} className={cls}>
                    {t.label}
                  </Link>
                );
              }
              return (
                <span
                  key={t.key}
                  className={cn(cls, "cursor-default text-ink-400 hover:text-ink-400")}
                  title="Coming soon"
                >
                  {t.label}
                </span>
              );
            })}
          </nav>
        </div>

        {/* Columns canvas */}
        <div className="flex-1 overflow-x-auto bg-ink-50 px-6 py-4">
          <div
            className="flex h-full gap-3 pb-4"
            style={{ minWidth: `${board.columns.length * 280}px` }}
          >
            {board.columns.map((col) => (
              <div
                key={col.status_name}
                className={cn(
                  "flex min-w-[260px] flex-1 flex-col rounded bg-ink-100/70 px-2.5 py-2",
                  dragOver === col.status_name && "ring-2 ring-brand-500 ring-offset-2",
                )}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(col.status_name);
                }}
                onDragLeave={() => setDragOver(null)}
                onDrop={(e) => onDrop(col.status_name, e)}
              >
                <div className="mb-2 flex items-center justify-between px-1">
                  <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-600">
                    {col.status_name}
                    <span className="ml-1.5 text-ink-400">{col.cards.length}</span>
                  </h3>
                </div>
                <div className="flex flex-col gap-2 overflow-y-auto scrollbar-thin">
                  {col.cards.map((card) => (
                    <IssueCard key={card.issue.id} issue={card.issue} />
                  ))}
                  {col.cards.length === 0 && (
                    <div className="py-4 text-center text-[11px] italic text-ink-400">
                      Drag issues here
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}

function Skeleton() {
  return (
    <div className="px-6 py-4 animate-pulse">
      <div className="h-6 w-1/3 bg-ink-200 mb-4" />
      <div className="flex gap-3">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="flex-1 h-64 bg-ink-100 rounded" />
        ))}
      </div>
    </div>
  );
}
