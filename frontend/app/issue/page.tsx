"use client";

import {
  ArrowDownUp,
  Calendar,
  ChevronDown,
  ChevronRight,
  Eye,
  EyeOff,
  Link2,
  Lock,
  Maximize2,
  MessageSquare,
  Minimize2,
  MoreHorizontal,
  Pencil,
  Plus,
  Settings,
  Share2,
  Sparkles,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Avatar } from "@/components/Avatar";
import { Dropdown } from "@/components/Dropdown";
import { IssueTypeIcon } from "@/components/IssueTypeIcon";
import { MentionText } from "@/components/MentionText";
import { MentionTextarea } from "@/components/MentionTextarea";
import { PriorityBadge } from "@/components/PriorityBadge";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api";
import { TESTID, testId } from "@/lib/jira-testids";
import type { Activity, Comment, IssueDetail, Sprint, User, UserMe } from "@/lib/types";
import { absoluteTime, cn, relativeTime } from "@/lib/utils";

const PRIORITIES = ["Highest", "High", "Medium", "Low", "Lowest"] as const;
type Priority = (typeof PRIORITIES)[number];

export default function IssuePage() {
  const params = useSearchParams();
  const id = params.get("id");
  const [issue, setIssue] = useState<IssueDetail | null>(null);
  const [history, setHistory] = useState<Activity[]>([]);
  const [users, setUsers] = useState<Record<string, User>>({});
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [me, setMe] = useState<UserMe | null>(null);
  const [tab, setTab] = useState<"all" | "comments" | "history" | "worklog">("all");
  const [sortAsc, setSortAsc] = useState(false);
  const [devOpen, setDevOpen] = useState(true);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pendingTransition, setPendingTransition] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!id) return;
    const i = await api.issue(id);
    setIssue(i);
    const h = await api.history(id);
    setHistory(h);
  }, [id]);

  useEffect(() => {
    refresh().catch((e) => setError(e.message));
    api.users().then((list) => {
      const map: Record<string, User> = {};
      list.forEach((u) => (map[u.id] = u));
      setUsers(map);
    });
    api.me().then(setMe).catch(() => {});
  }, [refresh]);

  // Fetch sprints for the current project once we know the issue.
  useEffect(() => {
    if (!issue) return;
    api.sprints(issue.project_key).then(setSprints).catch(() => {});
  }, [issue?.project_key]);

  // Generic helper that runs a service call, refreshes, and surfaces errors.
  // Centralising this keeps every editor (priority, sprint, reporter, ...)
  // a one-liner.
  async function mutate<T>(fn: () => Promise<T>) {
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (!id) return <AppShell><div className="p-8 text-ink-500">Missing issue id.</div></AppShell>;
  if (error) {
    return (
      <AppShell>
        <div className="p-8">
          <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        </div>
      </AppShell>
    );
  }
  if (!issue) return <AppShell><div className="p-8 animate-pulse text-ink-500">Loading…</div></AppShell>;

  async function transition(toStatus: string) {
    if (!issue) return;
    setPendingTransition(toStatus);
    const prev = { status: issue.status, board_list: issue.board_list };
    setIssue({ ...issue, status: toStatus });
    try {
      await api.transition(issue.id, toStatus);
      await refresh();
    } catch (e: any) {
      setError(e.message);
      setIssue({ ...issue, status: prev.status, board_list: prev.board_list });
    } finally {
      setPendingTransition(null);
    }
  }

  async function submitComment() {
    if (!issue || !comment.trim()) return;
    try {
      await api.comment(issue.id, comment.trim());
      setComment("");
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <AppShell>
      <div
        className="px-6 py-4 max-w-[1440px]"
        data-testid={TESTID.issuePage.container}
      >
        {/*
          Top row, modeled on the Jira screenshot:
            ┌──────────────────────────────────────────────────────────────────────────┐
            │ Add epic / KEY                                  🔒 👁 1 ⇗ ⚡ ⋯ ⤡ ✕        │
            └──────────────────────────────────────────────────────────────────────────┘
          Lock / share / minimize / close are chrome-only on the modal view in
          real Jira — we render them visible-but-inert because DOM-driven agents
          query for them and they keep the visual rhythm honest.
        */}
        <div className="mb-3 flex items-center justify-between">
          <Breadcrumb
            issue={issue}
            data-testid={TESTID.issuePage.breadcrumb}
          />
          <div className="flex items-center gap-0.5">
            <ChromeIcon ariaLabel="Lock issue" testid={TESTID.issuePage.toolbar.lock}>
              <Lock size={13} />
            </ChromeIcon>
            {me && (
              <WatchToggle
                watching={issue.watchers.includes(me.id)}
                count={issue.watchers.length}
                onToggle={(watching) =>
                  mutate(() => (watching ? api.watch(issue.id) : api.unwatch(issue.id)))
                }
              />
            )}
            <ChromeIcon ariaLabel="Share issue" testid={TESTID.issuePage.toolbar.share}>
              <Share2 size={13} />
            </ChromeIcon>
            <ChromeIcon ariaLabel="Automation" testid={TESTID.issuePage.toolbar.automation}>
              <Zap size={13} />
            </ChromeIcon>
            <ChromeIcon ariaLabel="More actions" testid={TESTID.issuePage.toolbar.more}>
              <MoreHorizontal size={13} />
            </ChromeIcon>
            <ChromeIcon ariaLabel="Minimize" testid={TESTID.issuePage.toolbar.minimize}>
              <Minimize2 size={13} />
            </ChromeIcon>
            <ChromeIcon ariaLabel="Close" testid={TESTID.issuePage.toolbar.close}>
              <X size={14} />
            </ChromeIcon>
          </div>
        </div>

        <div className="grid grid-cols-[minmax(0,_1fr)_360px] gap-6">
          <div className="min-w-0">
            {/*
              Title row. In Jira the per-issue action toolbar (Status /
              Agents / ⚡ / ✦ Improve) lives at the top of the *right* column,
              flush to the right edge of the page, not inline with the title.
              We render it there (see the aside below) so the two columns
              align vertically.
            */}
            <div className="mb-2">
              <SummaryEditor
                value={issue.summary}
                onSave={(s) =>
                  mutate(() => api.patchIssue(issue.id, { summary: s }))
                }
              />
            </div>

            {/* Plus / More — Jira's quick-actions row beneath the title. */}
            <div className="mb-5 flex items-center gap-1">
              <button
                type="button"
                aria-label="Add"
                title="Add"
                data-testid={TESTID.issuePage.title.addBelow}
                className="inline-flex h-6 w-6 items-center justify-center rounded border border-ink-200 text-ink-500 hover:bg-ink-100"
              >
                <Plus size={12} />
              </button>
              <button
                type="button"
                aria-label="More"
                title="More"
                data-testid={TESTID.issuePage.title.titleMore}
                className="inline-flex h-6 w-6 items-center justify-center rounded border border-ink-200 text-ink-500 hover:bg-ink-100"
              >
                <MoreHorizontal size={12} />
              </button>
            </div>

            {/* Description */}
            <Section
              title="Description"
              testid={TESTID.issuePage.description.container}
            >
              <DescriptionEditor
                value={issue.description}
                users={Object.values(users)}
                onSave={(d) =>
                  mutate(() => api.patchIssue(issue.id, { description: d }))
                }
              />
            </Section>

            {/* Subtasks */}
            <Section
              title="Subtasks"
              testid={TESTID.issuePage.subtasks.container}
              headerExtra={
                <button
                  type="button"
                  data-testid={TESTID.issuePage.subtasks.addButton}
                  className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[12px] text-ink-500 hover:bg-ink-100 hover:text-ink-700"
                  title="Subtask creation is not implemented in this environment yet."
                  aria-label="Add subtask"
                >
                  <Plus size={11} /> Add subtask
                </button>
              }
            >
              <p className="text-[12px] text-ink-400">Add subtask</p>
            </Section>

            {/* Linked work items — moved into the main column to match Jira. */}
            <Section
              title="Linked work items"
              testid={TESTID.issuePage.links.container}
            >
              <LinksGroupInline
                issue={issue}
                onAdd={(target, link_type) =>
                  mutate(() => api.linkIssue(issue.id, target, link_type))
                }
                onRemove={(target, link_type) =>
                  mutate(() => api.unlinkIssue(issue.id, target, link_type))
                }
              />
            </Section>

            {/* Activity tabs */}
            <Section
              title="Activity"
              testid={TESTID.issuePage.activity.container}
              headerExtra={
                <button
                  type="button"
                  data-testid={TESTID.issuePage.activity.sort}
                  aria-label="Sort activity"
                  onClick={() => setSortAsc((v) => !v)}
                  className="rounded p-1 text-ink-500 hover:bg-ink-100"
                >
                  <ArrowDownUp size={13} />
                </button>
              }
            >
              <div
                role="tablist"
                className="mb-3 flex items-center gap-1 rounded bg-ink-100/50 p-0.5 text-[13px]"
              >
                <ActivityTab
                  active={tab === "all"}
                  onClick={() => setTab("all")}
                  testid={TESTID.issuePage.activity.tab("all")}
                >
                  All
                </ActivityTab>
                <ActivityTab
                  active={tab === "comments"}
                  onClick={() => setTab("comments")}
                  testid={TESTID.issuePage.activity.tab("comments")}
                >
                  Comments
                </ActivityTab>
                <ActivityTab
                  active={tab === "history"}
                  onClick={() => setTab("history")}
                  testid={TESTID.issuePage.activity.tab("history")}
                >
                  History
                </ActivityTab>
                <ActivityTab
                  active={tab === "worklog"}
                  onClick={() => setTab("worklog")}
                  testid={TESTID.issuePage.activity.tab("worklog")}
                >
                  Work log
                </ActivityTab>
              </div>

              {(tab === "comments" || tab === "all") && (
                <div
                  className="space-y-3"
                  data-testid={TESTID.issuePage.activity.list}
                >
                  {sortedComments(issue.recent_comments || [], sortAsc).map((c) => (
                    <CommentCard
                      key={c.id}
                      comment={c}
                      users={users}
                      canEdit={!!me && (me.id === c.author_id || me.role === "admin")}
                      onSave={(body) =>
                        mutate(() => api.updateComment(issue.id, c.id, body))
                      }
                      onDelete={() =>
                        mutate(() => api.deleteComment(issue.id, c.id))
                      }
                    />
                  ))}
                  <div
                    className="rounded border border-ink-200 bg-white p-3"
                    data-testid={TESTID.issuePage.activity.addComment}
                  >
                    <MentionTextarea
                      rows={3}
                      placeholder="Add a comment… use @username to tag someone. Markdown supported."
                      value={comment}
                      onChange={setComment}
                      users={Object.values(users)}
                      className="w-full resize-none rounded border border-ink-200 px-2 py-1.5 text-sm focus:border-brand-500 focus:outline-none"
                    />
                    <div className="mt-2 flex justify-end">
                      <button
                        type="button"
                        disabled={!comment.trim()}
                        onClick={submitComment}
                        data-testid={TESTID.issuePage.activity.commentSubmit}
                        className="rounded bg-brand-500 px-3 py-1.5 text-xs text-white hover:bg-brand-600 disabled:opacity-50"
                      >
                        <MessageSquare size={12} className="inline mr-1" />
                        Save
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {(tab === "history" || tab === "all") && (
                <ul
                  className={cn("space-y-2", tab === "all" && "mt-4 border-t border-ink-100 pt-3")}
                >
                  {sortedHistory(history, sortAsc).map((a) => (
                    <li
                      key={a.id}
                      data-testid={TESTID.issuePage.activity.historyItem(a.id)}
                      className="flex items-start gap-2 text-sm"
                    >
                      <Avatar
                        name={users[a.actor_id]?.name}
                        color={users[a.actor_id]?.avatar_color}
                        size={20}
                      />
                      <div className="flex-1">
                        <span className="text-ink-700">
                          <strong>{users[a.actor_id]?.name || a.actor_id}</strong>{" "}
                          {describeActivity(a)}
                        </span>
                        <div className="text-[11px] text-ink-400">
                          {relativeTime(a.created_at)}
                          {tab === "all" && (
                            <span className="ml-2 rounded bg-ink-100 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-ink-500">
                              History
                            </span>
                          )}
                        </div>
                      </div>
                      <span
                        className="text-[11px] text-ink-400"
                        title={absoluteTime(a.created_at)}
                      >
                        {relativeTime(a.created_at)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              {tab === "worklog" && (
                <p className="text-[12px] text-ink-400">
                  No work logged yet. Tracking time-spent is not implemented in
                  this environment.
                </p>
              )}
            </Section>
          </div>

          {/* ----- Right panel ------------------------------------------------- */}
          <aside
            className="sticky top-2 self-start space-y-3"
            data-testid={TESTID.issuePage.details.container}
          >
            {/*
              Per-issue action toolbar — sits at the top of the right column
              so it lines up with the issue title on the left, with the rightmost
              button (Improve) flush against the right edge of the page.
            */}
            <div className="flex justify-end">
              <TopActionBar
                issue={issue}
                category={categoryFromStatus(issue, history)}
                allowed={issue.allowed_transitions}
                disabled={!!pendingTransition}
                onTransition={transition}
              />
            </div>

            <div className="rounded border border-ink-200 bg-white">
              <DetailsHeader title="Details" gearTestid={TESTID.issuePage.details.gear} />
              <div className="space-y-2 px-3 py-3">
                <DetailRow
                  label="Assignee"
                  testid={TESTID.issuePage.details.assignee}
                  trailing={
                    me &&
                    me.id !== issue.owner && (
                      <button
                        type="button"
                        data-testid={TESTID.issuePage.details.assigneeAssignToMe}
                        onClick={() => mutate(() => api.assign(issue.id, me.id))}
                        className="text-[11px] font-medium text-brand-600 hover:underline"
                      >
                        Assign to me
                      </button>
                    )
                  }
                >
                  <UserPicker
                    users={users}
                    value={issue.owner}
                    allowNull
                    nullLabel="Unassigned"
                    onChange={(uid) => mutate(() => api.assign(issue.id, uid))}
                  />
                </DetailRow>
                <DetailRow label="Priority" testid={TESTID.issuePage.details.priority}>
                  <PriorityPicker
                    value={issue.priority as Priority}
                    onChange={(p) =>
                      mutate(() => api.patchIssue(issue.id, { priority: p }))
                    }
                  />
                </DetailRow>
                <DetailRow label="Parent" testid={TESTID.issuePage.details.parent}>
                  <IssueRefEditor
                    value={issue.parent_id}
                    placeholder="PLAT-12"
                    onChange={(v) =>
                      mutate(() => api.patchIssue(issue.id, { parent_id: v }))
                    }
                  />
                </DetailRow>
                <DetailRow label="Due date" testid={TESTID.issuePage.details.dueDate}>
                  <DueDateEditor
                    value={issue.due_date}
                    onChange={(d) =>
                      mutate(() => api.patchIssue(issue.id, { due_date: d }))
                    }
                  />
                </DetailRow>
                <DetailRow label="Labels" testid={TESTID.issuePage.details.labels}>
                  <LabelsEditor
                    labels={issue.labels}
                    onAdd={(l) => mutate(() => api.addLabel(issue.id, l))}
                    onRemove={(l) => mutate(() => api.removeLabel(issue.id, l))}
                  />
                </DetailRow>
                <DetailRow label="Team" testid={TESTID.issuePage.details.team}>
                  <NoneValue />
                </DetailRow>
                <DetailRow label="Start date" testid={TESTID.issuePage.details.startDate}>
                  <NoneValue />
                </DetailRow>
                <DetailRow label="Sprint" testid={TESTID.issuePage.details.sprint}>
                  <SprintPicker
                    sprints={sprints}
                    value={issue.sprint_id}
                    onChange={(sid) => mutate(() => api.setSprint(issue.id, sid))}
                  />
                </DetailRow>
                <DetailRow
                  label="Story point estimate"
                  testid={TESTID.issuePage.details.storyPoints}
                >
                  <StoryPointsEditor
                    value={issue.story_points}
                    onChange={(sp) =>
                      mutate(() => api.patchIssue(issue.id, { story_points: sp }))
                    }
                  />
                </DetailRow>
                <DetailRow label="Reporter" testid={TESTID.issuePage.details.reporter}>
                  <UserPicker
                    users={users}
                    value={issue.reporter}
                    onChange={(uid) =>
                      uid &&
                      mutate(() =>
                        api.patchIssue(issue.id, { reporter: uid }),
                      )
                    }
                  />
                </DetailRow>
              </div>
            </div>

            {/* Development - collapsible affordance to match Jira; the
                section is a placeholder because this env doesn't integrate
                a real source-control plane. */}
            <div
              className="rounded border border-ink-200 bg-white"
              data-testid={TESTID.issuePage.development.container}
            >
              <button
                type="button"
                onClick={() => setDevOpen((v) => !v)}
                className="flex w-full items-center gap-1.5 border-b border-ink-100 px-3 py-2 text-[12px] font-semibold text-ink-700 hover:bg-ink-50"
                aria-expanded={devOpen}
                data-testid={TESTID.issuePage.development.heading}
              >
                {devOpen ? (
                  <ChevronDown size={12} />
                ) : (
                  <ChevronRight size={12} />
                )}
                Development
              </button>
              {devOpen && (
                <div className="px-3 py-3 text-[12px] text-ink-500">
                  Connect to source control to see branches, commits, and pull
                  requests here.
                </div>
              )}
            </div>

            <div className="px-2 text-[11px] text-ink-400">
              Created {relativeTime(issue.created_at)} · Updated{" "}
              {relativeTime(issue.updated_at)}
            </div>
          </aside>
        </div>
      </div>
    </AppShell>
  );
}

// ===== New helpers used by the rebuilt layout ============================

function Breadcrumb({
  issue,
  ...rest
}: {
  issue: IssueDetail;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <nav
      className="text-[12px] text-ink-500 flex items-center gap-1.5"
      aria-label="Breadcrumb"
      {...rest}
    >
      {issue.epic_id ? (
        <Link
          href={`/issue?id=${issue.epic_id}`}
          className="inline-flex items-center gap-1 hover:underline"
          data-testid={TESTID.issuePage.parentLink}
        >
          <IssueTypeIcon type="Epic" size={12} />
          {issue.epic_id}
        </Link>
      ) : (
        <span className="inline-flex items-center gap-1 text-ink-500">
          <Pencil size={12} aria-hidden /> Add epic
        </span>
      )}
      <span>/</span>
      <Link
        href={`/issue?id=${issue.id}`}
        className="inline-flex items-center gap-1 font-mono text-brand-600 hover:underline"
        data-testid={TESTID.issuePage.keyLink}
      >
        <IssueTypeIcon type={issue.issue_type} size={12} />
        {issue.id}
      </Link>
    </nav>
  );
}

function ChromeIcon({
  children,
  ariaLabel,
  testid,
  onClick,
}: {
  children: React.ReactNode;
  ariaLabel: string;
  testid?: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      title={ariaLabel}
      data-testid={testid}
      onClick={onClick}
      className="inline-flex h-7 w-7 items-center justify-center rounded text-ink-500 hover:bg-ink-100 hover:text-ink-700"
    >
      {children}
    </button>
  );
}

function TopActionBar({
  issue,
  category,
  allowed,
  disabled,
  onTransition,
}: {
  issue: IssueDetail;
  category: "todo" | "in_progress" | "done";
  allowed: { to_status_name: string; name: string }[];
  disabled: boolean;
  onTransition: (s: string) => void;
}) {
  return (
    <div
      className="flex shrink-0 items-center gap-1.5"
      data-testid={TESTID.issuePage.toolbar.container}
    >
      <div data-testid={TESTID.issuePage.toolbar.status}>
        <TransitionMenu
          current={issue.status || ""}
          category={category}
          allowed={allowed}
          disabled={disabled}
          onSelect={onTransition}
        />
      </div>
      <button
        type="button"
        data-testid={TESTID.issuePage.toolbar.agents}
        className="inline-flex items-center gap-1 rounded border border-ink-200 bg-white px-2 py-1 text-[12px] text-ink-700 hover:bg-ink-50"
        title="Open agent panel (not implemented)"
      >
        Agents
      </button>
      <button
        type="button"
        data-testid={TESTID.issuePage.toolbar.automation}
        aria-label="Automation"
        className="inline-flex h-7 w-7 items-center justify-center rounded border border-ink-200 bg-white text-ink-500 hover:bg-ink-50"
      >
        <Zap size={13} />
      </button>
      <button
        type="button"
        data-testid={TESTID.issuePage.toolbar.improve}
        className="inline-flex items-center gap-1 rounded border border-ink-200 bg-white px-2 py-1 text-[12px] text-ink-700 hover:bg-ink-50"
        title={`Improve this ${issue.issue_type.toLowerCase()} with AI (not implemented).`}
      >
        <Sparkles size={12} className="text-brand-500" />
        <span>Improve {issue.issue_type}</span>
      </button>
    </div>
  );
}

function Section({
  title,
  children,
  testid,
  headerExtra,
}: {
  title: string;
  children: React.ReactNode;
  testid?: string;
  headerExtra?: React.ReactNode;
}) {
  return (
    <section className="mb-6" data-testid={testid}>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-[14px] font-semibold text-ink-800">{title}</h2>
        {headerExtra}
      </div>
      {children}
    </section>
  );
}

function ActivityTab({
  active,
  onClick,
  children,
  testid,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  testid?: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      data-testid={testid}
      onClick={onClick}
      className={cn(
        "rounded px-2.5 py-1 text-[12px] font-medium transition",
        active
          ? "bg-white text-ink-900 shadow-sm"
          : "text-ink-600 hover:text-ink-800",
      )}
    >
      {children}
    </button>
  );
}

function DetailsHeader({
  title,
  gearTestid,
}: {
  title: string;
  gearTestid: string;
}) {
  return (
    <div
      className="flex items-center justify-between border-b border-ink-100 px-3 py-2"
      data-testid={TESTID.issuePage.details.heading}
    >
      <span className="text-[12px] font-semibold uppercase tracking-wide text-ink-700">
        {title}
      </span>
      <button
        type="button"
        aria-label="Configure details panel"
        data-testid={gearTestid}
        className="rounded p-0.5 text-ink-400 hover:bg-ink-100 hover:text-ink-700"
      >
        <Settings size={12} />
      </button>
    </div>
  );
}

function NoneValue() {
  return <span className="text-[13px] text-ink-400">None</span>;
}

function sortedComments(comments: Comment[], asc: boolean): Comment[] {
  const out = [...comments];
  out.sort((a, b) =>
    asc
      ? a.created_at.localeCompare(b.created_at)
      : b.created_at.localeCompare(a.created_at),
  );
  return out;
}

function sortedHistory(history: Activity[], asc: boolean): Activity[] {
  const out = [...history];
  out.sort((a, b) =>
    asc
      ? a.created_at.localeCompare(b.created_at)
      : b.created_at.localeCompare(a.created_at),
  );
  return out;
}

function categoryFromStatus(issue: IssueDetail, _h: Activity[]): "todo" | "in_progress" | "done" {
  // Crude: infer from issue.status string. Server returns this in allowed_transitions but
  // we can derive from board_list category sets at build time. Cheap approximation:
  if (["Done", "Closed", "Resolved"].includes(issue.status || "")) return "done";
  if (["In Progress", "In Review", "Working", "Waiting"].includes(issue.status || ""))
    return "in_progress";
  return "todo";
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      className={cn(
        "py-2 -mb-px border-b-2 text-sm",
        active
          ? "border-brand-500 text-ink-900 font-medium"
          : "border-transparent text-ink-500 hover:text-ink-800",
      )}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function DetailGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded border border-ink-200 bg-white">
      <div className="px-3 py-2 border-b border-ink-200 text-[11px] font-semibold uppercase tracking-wide text-ink-700">
        {title}
      </div>
      <div className="px-3 py-2 space-y-2">{children}</div>
    </div>
  );
}

function DetailRow({
  label,
  children,
  testid,
  trailing,
}: {
  label: string;
  children: React.ReactNode;
  testid?: string;
  trailing?: React.ReactNode;
}) {
  return (
    <div
      className="grid grid-cols-[110px_1fr] items-start gap-x-2 text-sm"
      data-testid={testid ? `${testid}.field` : undefined}
    >
      <span className="pt-1 text-[12px] text-ink-500">{label}</span>
      <div data-testid={testid}>
        <div className="min-h-[24px]">{children}</div>
        {trailing && <div className="mt-0.5">{trailing}</div>}
      </div>
    </div>
  );
}

function TransitionMenu({
  current,
  category,
  allowed,
  disabled,
  onSelect,
}: {
  current: string;
  category: "todo" | "in_progress" | "done";
  allowed: { to_status_name: string; name: string }[];
  disabled: boolean;
  onSelect: (s: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        type="button"
        className="inline-flex items-center gap-1.5 rounded border border-ink-200 px-2 py-1 text-sm font-medium hover:bg-ink-100 disabled:opacity-50"
        disabled={disabled || allowed.length === 0}
        onClick={() => setOpen((v) => !v)}
      >
        <StatusBadge name={current} category={category} />
        <ChevronDown size={14} />
      </button>
      {open && (
        <ul className="absolute z-10 mt-1 rounded border border-ink-200 bg-white shadow-pop min-w-[180px] py-1">
          {allowed.length === 0 && (
            <li className="px-3 py-1.5 text-xs text-ink-400">No transitions available.</li>
          )}
          {allowed.map((t) => (
            <li key={t.to_status_name}>
              <button
                type="button"
                className="w-full text-left px-3 py-1.5 text-sm hover:bg-ink-50"
                onClick={() => {
                  setOpen(false);
                  onSelect(t.to_status_name);
                }}
              >
                {t.name} → <span className="text-ink-500">{t.to_status_name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Small click-outside helper used by every popover below. Without it, opening
 * one picker and clicking another piece of UI leaves the menu hanging open.
 */
function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);
  return { open, setOpen, ref };
}

function UserPicker({
  users,
  value,
  allowNull = false,
  nullLabel = "—",
  onChange,
}: {
  users: Record<string, User>;
  value: string | null;
  allowNull?: boolean;
  nullLabel?: string;
  onChange: (uid: string | null) => void;
}) {
  const { open, setOpen, ref } = usePopover();
  const [query, setQuery] = useState("");
  const current = value ? users[value] : null;
  const sortedUsers = useMemo(
    () =>
      Object.values(users)
        .sort((a, b) => a.name.localeCompare(b.name))
        .filter((u) => !query || u.name.toLowerCase().includes(query.toLowerCase())),
    [users, query],
  );
  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        className="inline-flex items-center gap-1.5 rounded border border-ink-200 px-1.5 py-0.5 text-sm hover:bg-ink-100"
        onClick={() => setOpen((v) => !v)}
      >
        {current ? (
          <>
            <Avatar name={current.name} color={current.avatar_color} size={20} />
            <span>{current.name}</span>
          </>
        ) : (
          <span className="text-ink-500">{nullLabel}</span>
        )}
        <ChevronDown size={12} className="text-ink-400" />
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 rounded border border-ink-200 bg-white shadow-pop py-1 w-[240px]">
          <input
            autoFocus
            placeholder="Filter…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="mx-2 mb-1 mt-0.5 block w-[calc(100%-1rem)] rounded border border-ink-200 px-2 py-1 text-xs focus:border-brand-500 focus:outline-none"
          />
          <div className="max-h-64 overflow-y-auto scrollbar-thin">
            {allowNull && (
              <button
                type="button"
                className="w-full text-left px-3 py-1.5 text-sm hover:bg-ink-50 text-ink-500"
                onClick={() => {
                  setOpen(false);
                  onChange(null);
                }}
              >
                {nullLabel}
              </button>
            )}
            {sortedUsers.map((u) => (
              <button
                type="button"
                key={u.id}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-ink-50"
                onClick={() => {
                  setOpen(false);
                  onChange(u.id);
                }}
              >
                <Avatar name={u.name} color={u.avatar_color} size={20} />
                {u.name}
              </button>
            ))}
            {sortedUsers.length === 0 && (
              <div className="px-3 py-2 text-xs text-ink-400">No matches.</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function PriorityPicker({
  value,
  onChange,
}: {
  value: Priority;
  onChange: (p: Priority) => void;
}) {
  const { open, setOpen, ref } = usePopover();
  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        className="inline-flex items-center gap-1.5 rounded border border-ink-200 px-1.5 py-0.5 text-sm hover:bg-ink-100"
        onClick={() => setOpen((v) => !v)}
      >
        <PriorityBadge priority={value} size={14} />
        <span>{value}</span>
        <ChevronDown size={12} className="text-ink-400" />
      </button>
      {open && (
        <ul className="absolute right-0 z-20 mt-1 w-[160px] rounded border border-ink-200 bg-white py-1 shadow-pop">
          {PRIORITIES.map((p) => (
            <li key={p}>
              <button
                type="button"
                className={cn(
                  "flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-ink-50",
                  p === value && "bg-ink-50 font-medium",
                )}
                onClick={() => {
                  setOpen(false);
                  if (p !== value) onChange(p);
                }}
              >
                <PriorityBadge priority={p} size={14} />
                {p}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function StoryPointsEditor({
  value,
  onChange,
}: {
  value: number | null;
  onChange: (n: number | null) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value?.toString() ?? "");

  useEffect(() => {
    setDraft(value?.toString() ?? "");
  }, [value]);

  function commit() {
    setEditing(false);
    const trimmed = draft.trim();
    if (trimmed === "") {
      if (value !== null) onChange(null);
      return;
    }
    const n = Number(trimmed);
    if (!Number.isFinite(n) || n < 0) {
      setDraft(value?.toString() ?? "");
      return;
    }
    if (n !== value) onChange(Math.round(n));
  }

  if (editing) {
    return (
      <input
        autoFocus
        type="number"
        min={0}
        max={1000}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            setDraft(value?.toString() ?? "");
            setEditing(false);
          }
        }}
        className="w-20 rounded border border-ink-200 px-1.5 py-0.5 text-sm focus:border-brand-500 focus:outline-none"
      />
    );
  }
  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      className="rounded border border-transparent px-1.5 py-0.5 text-sm text-ink-800 hover:border-ink-200 hover:bg-ink-50"
    >
      {value ?? <span className="text-ink-400">—</span>}
    </button>
  );
}

function SprintPicker({
  sprints,
  value,
  onChange,
}: {
  sprints: Sprint[];
  value: string | null;
  onChange: (sid: string | null) => void;
}) {
  const { open, setOpen, ref } = usePopover();
  // Only offer non-closed sprints as destinations (you can't move into a closed
  // sprint), but show the current sprint even if it happens to be closed so
  // the label is correct.
  const options = useMemo(
    () =>
      sprints
        .filter((s) => s.state !== "closed" || s.id === value)
        .sort((a, b) =>
          a.state === b.state
            ? (a.start_date || "").localeCompare(b.start_date || "")
            : a.state === "active"
              ? -1
              : b.state === "active"
                ? 1
                : 0,
        ),
    [sprints, value],
  );
  const current = sprints.find((s) => s.id === value) || null;
  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        className="inline-flex items-center gap-1.5 rounded border border-ink-200 px-1.5 py-0.5 text-left text-sm hover:bg-ink-100"
        onClick={() => setOpen((v) => !v)}
      >
        {current ? (
          <span className="truncate max-w-[200px]">{current.name}</span>
        ) : (
          <span className="text-ink-500">Backlog</span>
        )}
        <ChevronDown size={12} className="text-ink-400" />
      </button>
      {open && (
        <ul className="absolute right-0 z-20 mt-1 w-[300px] rounded border border-ink-200 bg-white py-1 shadow-pop">
          <li>
            <button
              type="button"
              className="w-full text-left px-3 py-1.5 text-sm text-ink-500 hover:bg-ink-50"
              onClick={() => {
                setOpen(false);
                if (value !== null) onChange(null);
              }}
            >
              Backlog (no sprint)
            </button>
          </li>
          {options.length === 0 && (
            <li className="px-3 py-2 text-xs text-ink-400">No open sprints.</li>
          )}
          {options.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                className={cn(
                  "flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm hover:bg-ink-50",
                  s.id === value && "bg-ink-50 font-medium",
                )}
                onClick={() => {
                  setOpen(false);
                  if (s.id !== value) onChange(s.id);
                }}
              >
                <span className="truncate">{s.name}</span>
                <span
                  className={cn(
                    "rounded px-1 text-[10px] uppercase",
                    s.state === "active"
                      ? "bg-green-100 text-green-700"
                      : s.state === "future"
                        ? "bg-blue-100 text-blue-700"
                        : "bg-ink-100 text-ink-500",
                  )}
                >
                  {s.state}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function LabelsEditor({
  labels,
  onAdd,
  onRemove,
}: {
  labels: string[];
  onAdd: (l: string) => void;
  onRemove: (l: string) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState("");
  function commit() {
    const v = draft.trim();
    setDraft("");
    setAdding(false);
    if (!v) return;
    if (labels.includes(v)) return;
    onAdd(v);
  }
  return (
    <div className="flex flex-wrap items-center gap-1">
      {labels.length === 0 && !adding && (
        <span className="text-sm text-ink-400">—</span>
      )}
      {labels.map((l) => (
        <span
          key={l}
          className="group inline-flex items-center gap-1 rounded bg-ink-100 px-1.5 py-0.5 text-[11px] text-ink-700"
        >
          {l}
          <button
            type="button"
            aria-label={`Remove ${l}`}
            onClick={() => onRemove(l)}
            className="rounded p-0.5 text-ink-400 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-ink-200 hover:text-ink-700"
          >
            <X size={10} />
          </button>
        </span>
      ))}
      {adding ? (
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
            if (e.key === "Escape") {
              setDraft("");
              setAdding(false);
            }
          }}
          placeholder="new-label"
          className="w-28 rounded border border-ink-200 px-1.5 py-0.5 text-[11px] focus:border-brand-500 focus:outline-none"
        />
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="inline-flex items-center gap-0.5 rounded border border-dashed border-ink-300 px-1 py-0.5 text-[11px] text-ink-500 hover:bg-ink-50"
        >
          <Plus size={10} /> Add
        </button>
      )}
    </div>
  );
}

function describeActivity(a: Activity): string {
  switch (a.action) {
    case "created": return `created the issue`;
    case "transitioned": return `moved status: ${a.from_value} → ${a.to_value}`;
    case "assigned": return a.to_value ? `assigned to ${a.to_value}` : "unassigned";
    case "commented": return `commented`;
    case "updated": return `changed ${a.field}: ${a.from_value || "—"} → ${a.to_value || "—"}`;
    case "labeled": return `added label "${a.to_value}"`;
    case "unlabeled": return `removed label "${a.from_value}"`;
    case "linked": return `linked: ${a.to_value}`;
    case "unlinked": return `removed link: ${a.from_value}`;
    case "sprint_added": return `added to sprint ${a.to_value}`;
    case "sprint_removed": return `removed from sprint ${a.from_value}`;
    case "sprint_started": return `started sprint`;
    case "sprint_completed": return `completed sprint`;
    case "watched": return `started watching`;
    case "unwatched": return `stopped watching`;
    case "mentioned": return `mentioned ${a.to_value}`;
    case "comment_edited": return `edited a comment`;
    case "comment_deleted": return `deleted a comment`;
    default: return a.action;
  }
}

function WatchToggle({
  watching,
  count,
  onToggle,
}: {
  watching: boolean;
  count: number;
  onToggle: (watching: boolean) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onToggle(!watching)}
      title={watching ? "Click to stop watching" : "Click to watch this issue"}
      className={cn(
        "inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px]",
        watching
          ? "border-brand-500 bg-brand-50 text-brand-700 hover:bg-brand-100"
          : "border-ink-200 text-ink-600 hover:bg-ink-100",
      )}
    >
      {watching ? <Eye size={11} /> : <EyeOff size={11} />}
      {watching ? "Watching" : "Watch"}
      <span className="text-ink-400">· {count}</span>
    </button>
  );
}

function SummaryEditor({
  value,
  onSave,
}: {
  value: string;
  onSave: (s: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  useEffect(() => {
    setDraft(value);
  }, [value]);

  function commit() {
    const trimmed = draft.trim();
    if (!trimmed) {
      setDraft(value);
      setEditing(false);
      return;
    }
    if (trimmed !== value) onSave(trimmed);
    setEditing(false);
  }

  if (editing) {
    return (
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            setDraft(value);
            setEditing(false);
          }
        }}
        className="w-full rounded border border-brand-500 px-2 py-1 text-xl font-semibold focus:outline-none"
      />
    );
  }
  return (
    <h1
      className="group cursor-text rounded text-xl font-semibold hover:bg-ink-50 -mx-2 px-2 py-1"
      title="Click to edit"
      onClick={() => setEditing(true)}
    >
      {value}
      <Pencil
        size={14}
        className="ml-2 inline opacity-0 text-ink-400 transition-opacity group-hover:opacity-100"
      />
    </h1>
  );
}

function DescriptionEditor({
  value,
  users,
  onSave,
}: {
  value: string | null;
  users: User[];
  onSave: (body: string | null) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || "");
  useEffect(() => {
    setDraft(value || "");
  }, [value]);

  function save() {
    const trimmed = draft.trim();
    const next = trimmed || null;
    if ((next || "") !== (value || "")) onSave(next);
    setEditing(false);
  }
  function cancel() {
    setDraft(value || "");
    setEditing(false);
  }

  if (!editing) {
    return (
      <div
        className="group cursor-text"
        onClick={() => setEditing(true)}
        title="Click to edit"
      >
        {value ? (
          <MentionText
            body={value}
            users={users}
            className="prose-sm rounded border border-ink-200 bg-white p-3 whitespace-pre-wrap text-sm text-ink-800 hover:border-ink-300"
          />
        ) : (
          <div className="rounded border border-dashed border-ink-200 bg-ink-50 px-3 py-3 text-sm text-ink-400 italic hover:border-ink-300 hover:text-ink-500">
            Click to add a description…
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="rounded border border-brand-500 bg-white">
      <MentionTextarea
        autoFocus
        rows={6}
        value={draft}
        onChange={setDraft}
        users={users}
        placeholder="Describe the work. @mention to tag teammates. Markdown supported."
        className="w-full resize-y rounded-t border-0 px-3 py-2 text-sm focus:outline-none"
      />
      <div className="flex items-center justify-end gap-2 border-t border-ink-100 px-2 py-1.5">
        <button
          type="button"
          onClick={cancel}
          className="rounded px-2 py-1 text-xs text-ink-500 hover:bg-ink-100"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={save}
          className="rounded bg-brand-500 px-2.5 py-1 text-xs text-white hover:bg-brand-600"
        >
          Save
        </button>
      </div>
    </div>
  );
}

function DueDateEditor({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (d: string | null) => void;
}) {
  const [draft, setDraft] = useState(value || "");
  useEffect(() => setDraft(value || ""), [value]);

  return (
    <div className="flex items-center gap-1">
      <Calendar size={12} className="text-ink-400" />
      <input
        type="date"
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value);
          onChange(e.target.value || null);
        }}
        className="rounded border border-ink-200 px-1 py-0.5 text-[12px] focus:border-brand-500 focus:outline-none"
      />
      {value && (
        <button
          type="button"
          title="Clear due date"
          aria-label="Clear due date"
          onClick={() => {
            setDraft("");
            onChange(null);
          }}
          className="rounded p-0.5 text-ink-400 hover:bg-ink-100 hover:text-ink-700"
        >
          <X size={11} />
        </button>
      )}
    </div>
  );
}

function IssueRefEditor({
  value,
  placeholder,
  onChange,
}: {
  value: string | null;
  placeholder: string;
  onChange: (v: string | null) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || "");
  useEffect(() => setDraft(value || ""), [value]);

  function commit() {
    const next = draft.trim().toUpperCase() || null;
    if (next !== value) onChange(next);
    setEditing(false);
  }

  if (editing) {
    return (
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            setDraft(value || "");
            setEditing(false);
          }
        }}
        placeholder={placeholder}
        className="w-full rounded border border-ink-200 px-1.5 py-0.5 text-[12px] font-mono focus:border-brand-500 focus:outline-none"
      />
    );
  }

  if (value) {
    return (
      <div className="group flex items-center gap-1">
        <Link
          className="font-mono text-sm text-brand-600 hover:underline"
          href={`/issue?id=${value}`}
        >
          {value}
        </Link>
        <button
          type="button"
          aria-label="Edit"
          onClick={() => setEditing(true)}
          className="rounded p-0.5 text-ink-400 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-ink-100"
        >
          <Pencil size={10} />
        </button>
        <button
          type="button"
          aria-label="Clear"
          onClick={() => onChange(null)}
          className="rounded p-0.5 text-ink-400 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-ink-100"
        >
          <X size={11} />
        </button>
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      className="text-[11px] text-ink-400 hover:text-ink-700"
    >
      None — set
    </button>
  );
}

function CommentCard({
  comment: c,
  users,
  canEdit,
  onSave,
  onDelete,
}: {
  comment: Comment;
  users: Record<string, User>;
  canEdit: boolean;
  onSave: (body: string) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(c.body);

  function save() {
    const trimmed = draft.trim();
    if (!trimmed || trimmed === c.body) {
      setEditing(false);
      return;
    }
    onSave(trimmed);
    setEditing(false);
  }

  return (
    <div className="group rounded border border-ink-200 bg-white p-3">
      <div className="flex items-center gap-2 mb-1">
        <Avatar
          name={users[c.author_id]?.name}
          color={users[c.author_id]?.avatar_color}
          size={22}
        />
        <span className="text-sm font-medium">
          {users[c.author_id]?.name || c.author_id}
        </span>
        <span
          className="text-[11px] text-ink-500"
          title={absoluteTime(c.created_at)}
        >
          {relativeTime(c.created_at)}
        </span>
        {c.edited_at && (
          <span
            className="text-[11px] text-ink-400 italic"
            title={`Edited ${absoluteTime(c.edited_at)}`}
          >
            (edited)
          </span>
        )}
        {canEdit && !editing && (
          <div className="ml-auto flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
            <button
              type="button"
              aria-label="Edit comment"
              onClick={() => {
                setDraft(c.body);
                setEditing(true);
              }}
              className="rounded p-1 text-ink-400 hover:bg-ink-100 hover:text-ink-700"
            >
              <Pencil size={12} />
            </button>
            <button
              type="button"
              aria-label="Delete comment"
              onClick={() => {
                if (window.confirm("Delete this comment? This cannot be undone.")) onDelete();
              }}
              className="rounded p-1 text-ink-400 hover:bg-red-50 hover:text-red-700"
            >
              <Trash2 size={12} />
            </button>
          </div>
        )}
      </div>
      {editing ? (
        <div className="rounded border border-brand-500">
          <MentionTextarea
            autoFocus
            rows={3}
            value={draft}
            onChange={setDraft}
            users={Object.values(users)}
            className="w-full resize-y rounded-t border-0 px-2 py-1.5 text-sm focus:outline-none"
          />
          <div className="flex justify-end gap-2 border-t border-ink-100 px-2 py-1.5">
            <button
              type="button"
              onClick={() => {
                setDraft(c.body);
                setEditing(false);
              }}
              className="rounded px-2 py-0.5 text-xs text-ink-500 hover:bg-ink-100"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={save}
              className="rounded bg-brand-500 px-2.5 py-0.5 text-xs text-white hover:bg-brand-600"
            >
              Save
            </button>
          </div>
        </div>
      ) : (
        <MentionText
          body={c.body}
          users={Object.values(users)}
          className="whitespace-pre-wrap text-sm text-ink-800"
        />
      )}
    </div>
  );
}

const LINK_TYPES = ["blocks", "relates", "duplicates", "clones", "causes"] as const;
type LinkType = (typeof LINK_TYPES)[number];

/**
 * In-body linked-issues editor. Renders the list of links + an inline
 * "Add linked work item" affordance matching the screenshot. Uses the same
 * Dropdown / API shapes the legacy sidebar `LinksGroup` used.
 */
function LinksGroupInline({
  issue,
  onAdd,
  onRemove,
}: {
  issue: IssueDetail;
  onAdd: (target: string, link_type: string) => void;
  onRemove: (target: string, link_type: string) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [target, setTarget] = useState("");
  const [linkType, setLinkType] = useState<LinkType>("blocks");

  function submit() {
    const t = target.trim().toUpperCase();
    if (!t) return;
    onAdd(t, linkType);
    setTarget("");
    setAdding(false);
  }

  const hasAny =
    issue.outbound_links.length > 0 || issue.inbound_links.length > 0;

  return (
    <div className="space-y-2">
      {hasAny && (
        <ul className="space-y-1">
          {issue.outbound_links.map((l) => (
            <li
              key={l.id}
              data-testid={TESTID.issuePage.links.item(l.target_id)}
              className="group flex items-center gap-2 text-sm"
            >
              <span className="w-24 shrink-0 text-[11px] uppercase tracking-wide text-ink-500">
                {l.link_type}
              </span>
              <Link
                href={`/issue?id=${l.target_id}`}
                className="font-mono text-brand-600 hover:underline"
              >
                {l.target_id}
              </Link>
              <button
                type="button"
                aria-label={`Remove ${l.link_type} link to ${l.target_id}`}
                onClick={() => onRemove(l.target_id, l.link_type)}
                className="ml-auto rounded p-0.5 text-ink-400 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-ink-200 hover:text-ink-700"
              >
                <X size={12} />
              </button>
            </li>
          ))}
          {issue.inbound_links.map((l) => (
            <li
              key={l.id}
              data-testid={TESTID.issuePage.links.item(l.source_id)}
              className="flex items-center gap-2 text-sm"
            >
              <span className="w-24 shrink-0 text-[11px] uppercase tracking-wide text-ink-500">
                is {l.link_type}ed by
              </span>
              <Link
                href={`/issue?id=${l.source_id}`}
                className="font-mono text-brand-600 hover:underline"
              >
                {l.source_id}
              </Link>
            </li>
          ))}
        </ul>
      )}
      {adding ? (
        <div className="flex items-center gap-1.5">
          <Dropdown<LinkType>
            value={linkType}
            options={LINK_TYPES.map((t) => ({ value: t, label: t }))}
            onChange={setLinkType}
            width={110}
            size="sm"
            label="Link type"
            testId={TESTID.issuePage.links.linkType}
          />
          <input
            autoFocus
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
              if (e.key === "Escape") {
                setTarget("");
                setAdding(false);
              }
            }}
            placeholder="Type, search or paste URL"
            data-testid={TESTID.issuePage.links.linkTarget}
            className="min-w-0 flex-1 rounded border border-ink-200 px-2 py-1 text-[13px] focus:border-brand-500 focus:outline-none"
          />
          <button
            type="button"
            onClick={submit}
            data-testid={TESTID.issuePage.links.submit}
            className="rounded bg-brand-500 px-2.5 py-1 text-[12px] text-white hover:bg-brand-600"
          >
            Link
          </button>
          <button
            type="button"
            onClick={() => {
              setAdding(false);
              setTarget("");
            }}
            className="rounded px-2 py-1 text-[12px] text-ink-500 hover:bg-ink-100"
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          data-testid={TESTID.issuePage.links.addButton}
          className="inline-flex items-center gap-1 text-[12px] text-ink-500 hover:text-ink-800"
        >
          <Link2 size={12} /> Add linked work item
        </button>
      )}
    </div>
  );
}

function LinksGroup({
  issue,
  onAdd,
  onRemove,
}: {
  issue: IssueDetail;
  onAdd: (target: string, link_type: string) => void;
  onRemove: (target: string, link_type: string) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [target, setTarget] = useState("");
  const [linkType, setLinkType] = useState<LinkType>("relates");

  function submit() {
    const t = target.trim().toUpperCase();
    if (!t) return;
    onAdd(t, linkType);
    setTarget("");
    setAdding(false);
  }

  return (
    <DetailGroup title="Linked issues">
      {issue.outbound_links.length === 0 && issue.inbound_links.length === 0 && (
        <div className="text-[11px] text-ink-400">No linked issues yet.</div>
      )}
      {issue.outbound_links.map((l) => (
        <div key={l.id} className="group flex items-center gap-2 text-sm">
          <span className="text-ink-500 text-[11px] w-20 shrink-0">{l.link_type}</span>
          <Link className="flex-1 hover:underline font-mono text-brand-600" href={`/issue?id=${l.target_id}`}>
            {l.target_id}
          </Link>
          <button
            type="button"
            aria-label={`Remove ${l.link_type} link to ${l.target_id}`}
            onClick={() => onRemove(l.target_id, l.link_type)}
            className="rounded p-0.5 text-ink-400 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-ink-200 hover:text-ink-700"
          >
            <X size={12} />
          </button>
        </div>
      ))}
      {issue.inbound_links.map((l) => (
        <div key={l.id} className="flex items-center gap-2 text-sm">
          <span className="text-ink-500 text-[11px] w-20 shrink-0">is {l.link_type}ed by</span>
          <Link className="flex-1 hover:underline font-mono text-brand-600" href={`/issue?id=${l.source_id}`}>
            {l.source_id}
          </Link>
        </div>
      ))}
      {adding ? (
        <div className="flex items-center gap-1.5 pt-1 border-t border-ink-100">
          <Dropdown<LinkType>
            value={linkType}
            options={LINK_TYPES.map((t) => ({ value: t, label: t }))}
            onChange={setLinkType}
            width={96}
            size="xs"
            label="Link type"
          />
          <input
            autoFocus
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
              if (e.key === "Escape") {
                setTarget("");
                setAdding(false);
              }
            }}
            placeholder="PLAT-12"
            className="min-w-0 flex-1 rounded border border-ink-200 px-1.5 py-0.5 text-[11px] focus:border-brand-500 focus:outline-none"
          />
          <button
            type="button"
            onClick={submit}
            className="rounded bg-brand-500 px-2 py-0.5 text-[11px] text-white hover:bg-brand-600"
          >
            Link
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="inline-flex items-center gap-1 rounded border border-dashed border-ink-300 px-1.5 py-0.5 text-[11px] text-ink-500 hover:bg-ink-50"
        >
          <Link2 size={11} /> Link issue
        </button>
      )}
    </DetailGroup>
  );
}
