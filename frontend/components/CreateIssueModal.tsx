"use client";

import {
  ArrowDown,
  ArrowUp,
  Calendar,
  ChevronDown,
  ChevronsDown,
  ChevronsUp,
  Flag,
  Maximize2,
  Minimize2,
  Minus,
  MoreHorizontal,
  Paperclip,
  Tag,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import { TESTID, testId } from "@/lib/jira-testids";
import type { Issue, Project, Sprint, User, UserMe } from "@/lib/types";
import { cn } from "@/lib/utils";

import { Avatar } from "./Avatar";
import { Dropdown, type DropdownOption } from "./Dropdown";
import { IssueTypeIcon } from "./IssueTypeIcon";
import { MentionTextarea } from "./MentionTextarea";

const ISSUE_TYPES = ["Task", "Story", "Bug", "Epic", "Subtask"] as const;
type IssueType = (typeof ISSUE_TYPES)[number];

const PRIORITIES = ["Highest", "High", "Medium", "Low", "Lowest"] as const;
type Priority = (typeof PRIORITIES)[number];

const PRIORITY_ICONS: Record<Priority, React.ReactNode> = {
  Highest: <ChevronsUp size={14} className="text-priority-highest" />,
  High: <ArrowUp size={14} className="text-priority-high" />,
  Medium: <Minus size={14} className="text-priority-medium" />,
  Low: <ArrowDown size={14} className="text-priority-low" />,
  Lowest: <ChevronsDown size={14} className="text-priority-lowest" />,
};

const LINK_TYPES = ["blocks", "relates", "duplicates", "clones", "causes"] as const;
type LinkType = (typeof LINK_TYPES)[number];

/**
 * Create Issue modal, modeled to match the screenshots from real Jira.
 *
 * Notes for DOM-driven agents:
 *
 *   - The root has `role="dialog"`, `aria-modal="true"`, `aria-labelledby`
 *     pointing at the title h2. Focus is trapped inside the dialog while
 *     it's open, returned to whatever opened it on close.
 *   - Each field has a stable `data-testid` from lib/jira-testids.ts. They
 *     mirror Atlassian's testid naming conventions
 *     (`issue-create.ui.modal.field.<name>`).
 *   - Required fields use `aria-required="true"` and `aria-invalid` toggles
 *     to indicate the validation state. Error messages are linked via
 *     `aria-describedby` so screen readers + DOM agents can pair them up.
 *   - The summary's "Summary is required" error is rendered when an attempt
 *     to submit happens with empty summary. It mirrors real Jira's wording.
 */
export function CreateIssueModal({
  projects,
  onClose,
  me,
}: {
  projects: Project[];
  onClose: () => void;
  me: User | null;
}) {
  const router = useRouter();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const summaryRef = useRef<HTMLInputElement | null>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const titleId = useId();

  // ------------------------- Field state --------------------------------
  const [projectKey, setProjectKey] = useState<string>(projects[0]?.key || "");
  const [issueType, setIssueType] = useState<IssueType>("Task");
  const [summary, setSummary] = useState("");
  const [showSummaryError, setShowSummaryError] = useState(false);
  const [description, setDescription] = useState("");
  const [assigneeId, setAssigneeId] = useState<string | null>(null); // null == Automatic
  const [priority, setPriority] = useState<Priority>("Medium");
  const [parentKey, setParentKey] = useState<string>("");
  const [dueDate, setDueDate] = useState<string>("");
  const [labels, setLabels] = useState<string[]>([]);
  const [team, setTeam] = useState<string>("");          // display-only
  const [startDate, setStartDate] = useState<string>(""); // display-only
  const [sprintId, setSprintId] = useState<string | null>(null);
  const [storyPoints, setStoryPoints] = useState<string>("");
  const [reporterId, setReporterId] = useState<string>(me?.id || "");
  const [linkType, setLinkType] = useState<LinkType>("blocks");
  const [linkTarget, setLinkTarget] = useState<string>("");
  const [restrictTo, setRestrictTo] = useState<string>("");
  const [flagged, setFlagged] = useState(false);
  const [createAnother, setCreateAnother] = useState(false);

  // Modal-level state
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [issueOptions, setIssueOptions] = useState<Issue[]>([]);

  // ------------------------- Load deps ----------------------------------
  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    api.users().then(setUsers).catch(() => {});
    return () => {
      previouslyFocused.current?.focus?.();
    };
  }, []);

  useEffect(() => {
    if (!me) return;
    setReporterId((cur) => cur || me.id);
  }, [me]);

  useEffect(() => {
    if (!projectKey) return;
    api.sprints(projectKey).then(setSprints).catch(() => setSprints([]));
    api
      .search(`project = ${projectKey} ORDER BY updated DESC`, 20, 0)
      .then((r) => setIssueOptions(r.issues))
      .catch(() => setIssueOptions([]));
  }, [projectKey]);

  // ------------------------- Focus trap ---------------------------------
  useEffect(() => {
    // Focus the summary input on mount so typing is immediate.
    requestAnimationFrame(() => summaryRef.current?.focus());

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key === "Tab" && dialogRef.current) {
        // Simple focus trap: cycle through focusable elements inside the modal.
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          [
            "a[href]",
            "button:not([disabled])",
            "input:not([disabled])",
            "textarea:not([disabled])",
            "select:not([disabled])",
            "[tabindex]:not([tabindex='-1'])",
          ].join(","),
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        const active = document.activeElement as HTMLElement;
        if (e.shiftKey && active === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  // ------------------------- Computed options ---------------------------
  const projectOptions: DropdownOption[] = useMemo(
    () =>
      projects.map((p) => ({
        value: p.key,
        label: `${p.name} (${p.key})`,
        icon: (
          <span
            className="inline-block h-3.5 w-3.5 shrink-0 rounded-sm"
            style={{ backgroundColor: p.avatar_color }}
          />
        ),
      })),
    [projects],
  );

  const issueTypeOptions: DropdownOption<IssueType>[] = useMemo(
    () =>
      ISSUE_TYPES.map((t) => ({
        value: t,
        label: t,
        icon: <IssueTypeIcon type={t} size={14} />,
      })),
    [],
  );

  const priorityOptions: DropdownOption<Priority>[] = useMemo(
    () =>
      PRIORITIES.map((p) => ({ value: p, label: p, icon: PRIORITY_ICONS[p] })),
    [],
  );

  const sprintOptions: DropdownOption[] = useMemo(
    () => [
      { value: "", label: "Select sprint" },
      ...sprints
        .filter((s) => s.state !== "closed")
        .map((s) => ({ value: s.id, label: s.name, hint: s.state })),
    ],
    [sprints],
  );

  const userOptions: DropdownOption[] = useMemo(
    () =>
      users.map((u) => ({
        value: u.id,
        label: u.display_name || u.name,
        icon: <Avatar name={u.name} color={u.avatar_color} size={20} />,
      })),
    [users],
  );

  const parentOptions: DropdownOption[] = useMemo(
    () => [
      { value: "", label: "Select parent" },
      ...issueOptions.map((i) => ({
        value: i.id,
        label: `${i.id} – ${i.summary}`,
        icon: <IssueTypeIcon type={i.issue_type} size={14} />,
      })),
    ],
    [issueOptions],
  );

  const labelInputId = useId();
  const summaryErrorId = useId();
  const reporterErrorId = useId();

  // ------------------------- Submit -------------------------------------
  async function submit() {
    if (!projectKey) {
      setError("Please choose a project.");
      return;
    }
    if (!summary.trim()) {
      setShowSummaryError(true);
      summaryRef.current?.focus();
      return;
    }
    if (!reporterId) {
      setError("Reporter is required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      // Reflect the "Flagged" checkbox as the "blocked" label, which is the
      // same convention the seed data uses and which surfaces inside the
      // /rest/api/3 Jira-compat layer as customfield_10019 (Impediment).
      const finalLabels = flagged
        ? Array.from(new Set([...labels, "blocked"]))
        : labels.filter((l) => l !== "blocked");
      const issue = await api.createIssue({
        project_key: projectKey,
        issue_type: issueType,
        summary: summary.trim(),
        description: description.trim() || null,
        priority,
        owner: assigneeId,
        labels: finalLabels,
        parent_id: parentKey || null,
        story_points: storyPoints ? Number(storyPoints) : null,
        due_date: dueDate || null,
        reporter: reporterId,
      } as any);

      // Sprint placement after-the-fact (the create endpoint doesn't accept
      // sprint_id directly; sprint membership is a separate write).
      if (sprintId) {
        try {
          await api.setSprint(issue.id, sprintId);
        } catch {
          /* non-fatal */
        }
      }
      // Link creation if specified.
      if (linkTarget.trim()) {
        try {
          await api.linkIssue(issue.id, linkTarget.trim().toUpperCase(), linkType);
        } catch {
          /* non-fatal */
        }
      }

      if (createAnother) {
        // Reset enough state to feel like "next issue", keeping project + type.
        setSummary("");
        setShowSummaryError(false);
        setDescription("");
        setAssigneeId(null);
        setLabels([]);
        setDueDate("");
        setStoryPoints("");
        setLinkTarget("");
        setFlagged(false);
        setSubmitting(false);
        summaryRef.current?.focus();
        return;
      }
      router.push(`/issue?id=${issue.id}`);
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-ink-900/30 pt-12 backdrop-blur-[1px]"
      onClick={onClose}
      data-testid={TESTID.createModal.container}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex h-[88vh] w-[540px] max-w-[92vw] flex-col rounded-md border border-ink-200 bg-white shadow-pop"
        onClick={(e) => e.stopPropagation()}
        data-testid={TESTID.createModal.dialog}
      >
        {/* Header */}
        <header className="flex items-center justify-between border-b border-ink-100 px-5 py-3">
          <h2
            id={titleId}
            className="text-[15px] font-semibold text-ink-900"
            data-testid={TESTID.createModal.header}
          >
            Create {issueType}
          </h2>
          <div className="flex items-center gap-0.5">
            <HeaderIcon ariaLabel="Minimize" testid={TESTID.createModal.minimize}>
              <Minimize2 size={14} />
            </HeaderIcon>
            <HeaderIcon ariaLabel="Expand" testid={TESTID.createModal.expand}>
              <Maximize2 size={14} />
            </HeaderIcon>
            <HeaderIcon ariaLabel="More actions" testid={TESTID.createModal.more}>
              <MoreHorizontal size={14} />
            </HeaderIcon>
            <HeaderIcon ariaLabel="Close" testid={TESTID.createModal.close} onClick={onClose}>
              <X size={16} />
            </HeaderIcon>
          </div>
        </header>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 pb-5 pt-3 scrollbar-thin">
          <p
            className="mb-4 text-[12px] text-ink-500"
            data-testid={TESTID.createModal.requiredLegend}
          >
            Required fields are marked with an asterisk <Asterisk />
          </p>

          {error && (
            <div
              role="alert"
              data-testid={TESTID.createModal.error}
              className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-[12px] text-red-700"
            >
              {error}
            </div>
          )}

          {/* Space (Project) */}
          <Field label="Space" required testid={TESTID.createModal.field.project}>
            <Dropdown
              value={projectKey}
              options={projectOptions}
              onChange={setProjectKey}
              size="md"
              label="Space"
              testId={TESTID.createModal.field.project}
              required
            />
          </Field>

          {/* Work type */}
          <Field label="Work type" required testid={TESTID.createModal.field.issueType}>
            <Dropdown<IssueType>
              value={issueType}
              options={issueTypeOptions}
              onChange={setIssueType}
              size="md"
              label="Work type"
              testId={TESTID.createModal.field.issueType}
              required
            />
          </Field>

          {/* Status */}
          <Field
            label="Status"
            testid={TESTID.createModal.field.status}
            help="This is the initial status upon creation"
          >
            <Dropdown
              value="todo"
              options={[{ value: "todo", label: "To Do" }]}
              onChange={() => {}}
              size="md"
              disabled
              label="Initial status"
              testId={TESTID.createModal.field.status}
            />
          </Field>

          {/* Summary */}
          <Field
            label="Summary"
            required
            testid={TESTID.createModal.field.summary}
            errorId={summaryErrorId}
          >
            <input
              ref={summaryRef}
              value={summary}
              onChange={(e) => {
                setSummary(e.target.value);
                if (showSummaryError) setShowSummaryError(false);
              }}
              onBlur={() => setShowSummaryError(!summary.trim())}
              aria-required="true"
              aria-invalid={showSummaryError || undefined}
              aria-describedby={showSummaryError ? summaryErrorId : undefined}
              data-testid={TESTID.createModal.field.summaryInput}
              className={cn(
                "w-full rounded border px-3 py-2 text-[14px] focus:outline-none focus:ring-1",
                showSummaryError
                  ? "border-red-500 focus:border-red-500 focus:ring-red-100"
                  : "border-ink-200 focus:border-brand-500 focus:ring-brand-100",
              )}
            />
            {showSummaryError && (
              <div
                id={summaryErrorId}
                role="alert"
                className="mt-1 flex items-center gap-1 text-[12px] text-red-600"
                data-testid={TESTID.createModal.field.summaryError}
              >
                <span aria-hidden>◆</span> Summary is required
              </div>
            )}
          </Field>

          {/* Description */}
          <Field label="Description" testid={TESTID.createModal.field.description}>
            <DescriptionEditor
              value={description}
              onChange={setDescription}
              users={users}
            />
          </Field>

          {/* Assignee */}
          <Field
            label="Assignee"
            testid={TESTID.createModal.field.assignee}
            trailing={
              me && (
                <button
                  type="button"
                  data-testid={TESTID.createModal.field.assigneeAssignToMe}
                  className="text-[12px] font-medium text-brand-600 hover:underline"
                  onClick={() => setAssigneeId(me.id)}
                >
                  Assign to me
                </button>
              )
            }
          >
            <Dropdown
              value={assigneeId || "automatic"}
              options={[
                {
                  value: "automatic",
                  label: "Automatic",
                  icon: (
                    <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-ink-100 text-[10px] text-ink-500">
                      ?
                    </span>
                  ),
                },
                ...userOptions,
              ]}
              onChange={(v) => setAssigneeId(v === "automatic" ? null : v)}
              size="md"
              label="Assignee"
              testId={TESTID.createModal.field.assignee}
            />
          </Field>

          {/* Priority */}
          <Field label="Priority" testid={TESTID.createModal.field.priority}>
            <Dropdown<Priority>
              value={priority}
              options={priorityOptions}
              onChange={setPriority}
              size="md"
              label="Priority"
              testId={TESTID.createModal.field.priority}
            />
          </Field>

          {/* Parent */}
          <Field
            label="Parent"
            testid={TESTID.createModal.field.parent}
            help="Your work type hierarchy determines the work items you can select here."
          >
            <Dropdown
              value={parentKey || ""}
              options={parentOptions}
              onChange={(v) => setParentKey(v === "" ? "" : v)}
              size="md"
              label="Parent"
              testId={TESTID.createModal.field.parent}
              placeholder="Select parent"
            />
          </Field>

          {/* Due date */}
          <Field label="Due date" testid={TESTID.createModal.field.dueDate}>
            <DateInput
              value={dueDate}
              onChange={setDueDate}
              testid={TESTID.createModal.field.dueDate}
            />
          </Field>

          {/* Labels */}
          <Field label="Labels" testid={TESTID.createModal.field.labels}>
            <LabelsInput labels={labels} onChange={setLabels} inputId={labelInputId} />
          </Field>

          {/* Team (display-only field) */}
          <Field
            label="Team"
            testid={TESTID.createModal.field.team}
            help="Associates a team to an issue. You can use this field to search and filter issues by team."
          >
            <Dropdown
              value={team}
              options={[
                { value: "", label: "Choose a team" },
                { value: "platform", label: "Platform" },
                { value: "support", label: "Customer Support" },
                { value: "mobile", label: "Mobile" },
              ]}
              onChange={setTeam}
              size="md"
              label="Team"
              testId={TESTID.createModal.field.team}
              placeholder="Choose a team"
            />
          </Field>

          {/* Start date */}
          <Field
            label="Start date"
            testid={TESTID.createModal.field.startDate}
            help="Allows the planned start date for a piece of work to be set."
          >
            <DateInput
              value={startDate}
              onChange={setStartDate}
              testid={TESTID.createModal.field.startDate}
            />
          </Field>

          {/* Sprint */}
          <Field
            label="Sprint"
            testid={TESTID.createModal.field.sprint}
            help="Jira Software sprint field"
          >
            <Dropdown
              value={sprintId || ""}
              options={sprintOptions}
              onChange={(v) => setSprintId(v || null)}
              size="md"
              label="Sprint"
              testId={TESTID.createModal.field.sprint}
              placeholder="Select sprint"
            />
          </Field>

          {/* Story points */}
          <Field
            label="Story point estimate"
            testid={TESTID.createModal.field.storyPoints}
            help="Measurement of complexity and/or size of a requirement."
          >
            <input
              type="number"
              value={storyPoints}
              onChange={(e) => setStoryPoints(e.target.value)}
              data-testid={TESTID.createModal.field.storyPoints}
              min={0}
              max={1000}
              className="w-full rounded border border-ink-200 px-3 py-2 text-[14px] focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-100"
            />
          </Field>

          {/* Reporter */}
          <Field label="Reporter" required testid={TESTID.createModal.field.reporter}>
            <Dropdown
              value={reporterId}
              options={userOptions}
              onChange={setReporterId}
              size="md"
              label="Reporter"
              testId={TESTID.createModal.field.reporter}
              required
            />
          </Field>

          {/* Attachment */}
          <Field label="Attachment" testid={TESTID.createModal.field.attachment}>
            <div className="flex w-full items-center justify-center gap-2 rounded border border-dashed border-ink-300 bg-ink-50 px-3 py-4 text-[12px] text-ink-500">
              <Paperclip size={14} />
              <span>Drop files to attach or</span>
              <button
                type="button"
                className="rounded border border-ink-300 bg-white px-2 py-0.5 text-[12px] text-ink-700 hover:bg-ink-100"
              >
                Browse
              </button>
            </div>
          </Field>

          {/* Linked work items */}
          <Field label="Linked work items" testid={TESTID.createModal.field.linkedIssues}>
            <div className="flex flex-col gap-2">
              <Dropdown<LinkType>
                value={linkType}
                options={LINK_TYPES.map((t) => ({ value: t, label: t }))}
                onChange={setLinkType}
                size="md"
                label="Link type"
                testId={TESTID.createModal.field.linkType}
              />
              <input
                value={linkTarget}
                onChange={(e) => setLinkTarget(e.target.value)}
                placeholder="Type, search or paste URL"
                data-testid={TESTID.createModal.field.linkTarget}
                className="w-full rounded border border-ink-200 px-3 py-2 text-[14px] focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-100"
              />
            </div>
          </Field>

          {/* Restrict to */}
          <Field label="Restrict to" testid={TESTID.createModal.field.restrictTo}>
            <Dropdown
              value={restrictTo}
              options={[
                { value: "", label: "Select Roles" },
                { value: "admins", label: "Admins" },
                { value: "leads", label: "Project Leads" },
              ]}
              onChange={setRestrictTo}
              size="md"
              label="Restrict to"
              testId={TESTID.createModal.field.restrictTo}
              placeholder="Select Roles"
            />
          </Field>

          {/* Flagged */}
          <Field label="Flagged" testid={TESTID.createModal.field.flagged}>
            <label className="flex cursor-pointer items-center gap-2 text-[13px] text-ink-700">
              <input
                type="checkbox"
                checked={flagged}
                onChange={(e) => setFlagged(e.target.checked)}
                data-testid={TESTID.createModal.field.flagged}
                className="h-4 w-4 rounded border-ink-300 text-brand-500 focus:ring-brand-100"
              />
              <Flag size={14} className="text-amber-500" />
              <span>Impediment</span>
            </label>
            <p className="mt-1 text-[12px] text-ink-500">
              Allows to flag issues with impediments.
            </p>
          </Field>
        </div>

        {/* Footer */}
        <footer className="flex items-center justify-between border-t border-ink-100 px-5 py-3">
          <label className="flex cursor-pointer items-center gap-2 text-[13px] text-ink-700">
            <input
              type="checkbox"
              checked={createAnother}
              onChange={(e) => setCreateAnother(e.target.checked)}
              data-testid={TESTID.createModal.createAnother}
              className="h-4 w-4 rounded border-ink-300 text-brand-500 focus:ring-brand-100"
            />
            Create another
          </label>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              data-testid={TESTID.createModal.cancel}
              className="rounded px-3 py-1.5 text-[13px] text-ink-700 hover:bg-ink-100"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={submit}
              data-testid={TESTID.createModal.submit}
              className="rounded bg-brand-500 px-3 py-1.5 text-[13px] font-medium text-white hover:bg-brand-600 disabled:opacity-50"
            >
              {submitting ? "Creating…" : "Create"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

// ----- Sub-components -------------------------------------------------------

function HeaderIcon({
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
      onClick={onClick}
      data-testid={testid}
      className="inline-flex h-7 w-7 items-center justify-center rounded text-ink-500 hover:bg-ink-100 hover:text-ink-700"
    >
      {children}
    </button>
  );
}

function Asterisk() {
  return <span className="text-red-600">*</span>;
}

function Field({
  label,
  required,
  children,
  testid,
  help,
  errorId,
  trailing,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
  testid?: string;
  help?: string;
  errorId?: string;
  trailing?: React.ReactNode;
}) {
  const id = useId();
  return (
    <div className="mb-4" data-testid={testid ? `${testid}.field` : undefined}>
      <div className="mb-1 flex items-baseline justify-between">
        <label
          htmlFor={id}
          className="text-[12px] font-semibold text-ink-700"
        >
          {label} {required && <Asterisk />}
        </label>
        {trailing}
      </div>
      <div id={id}>{children}</div>
      {help && (
        <p className="mt-1 text-[11px] leading-tight text-ink-500">{help}</p>
      )}
    </div>
  );
}

function DateInput({
  value,
  onChange,
  testid,
}: {
  value: string;
  onChange: (v: string) => void;
  testid?: string;
}) {
  return (
    <div className="relative">
      <input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        data-testid={testid ? `${testid}.input` : undefined}
        placeholder="Select date"
        className="w-full rounded border border-ink-200 px-3 py-2 text-[14px] focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-100"
      />
      <Calendar
        size={14}
        aria-hidden
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-ink-400"
      />
    </div>
  );
}

function LabelsInput({
  labels,
  onChange,
  inputId,
}: {
  labels: string[];
  onChange: (next: string[]) => void;
  inputId: string;
}) {
  const [draft, setDraft] = useState("");
  function commit() {
    const v = draft.trim().toLowerCase();
    setDraft("");
    if (!v || labels.includes(v)) return;
    onChange([...labels, v]);
  }
  return (
    <div className="flex flex-wrap items-center gap-1 rounded border border-ink-200 bg-white px-2 py-1.5 focus-within:border-brand-500 focus-within:ring-1 focus-within:ring-brand-100">
      <Tag size={13} aria-hidden className="text-ink-400" />
      {labels.map((l) => (
        <span
          key={l}
          className="inline-flex items-center gap-1 rounded bg-ink-100 px-1.5 py-0.5 text-[12px] text-ink-800"
        >
          {l}
          <button
            type="button"
            aria-label={`Remove ${l}`}
            onClick={() => onChange(labels.filter((x) => x !== l))}
            className="text-ink-500 hover:text-ink-700"
          >
            <X size={10} />
          </button>
        </span>
      ))}
      <input
        id={inputId}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            commit();
          } else if (e.key === "Backspace" && !draft && labels.length > 0) {
            onChange(labels.slice(0, -1));
          }
        }}
        onBlur={commit}
        placeholder={labels.length === 0 ? "Select label" : ""}
        className="min-w-[80px] flex-1 bg-transparent text-[13px] outline-none"
      />
    </div>
  );
}

function DescriptionEditor({
  value,
  onChange,
  users,
}: {
  value: string;
  onChange: (v: string) => void;
  users: User[];
}) {
  return (
    <div
      className="rounded border border-ink-200 focus-within:border-brand-500 focus-within:ring-1 focus-within:ring-brand-100"
      data-testid={TESTID.createModal.field.descriptionEditor}
    >
      {/* Toolbar facade — affordance-fidelity for vision agents that recognize
        the editor pattern; the buttons are non-functional formatting cues. */}
      <div className="flex items-center gap-1 border-b border-ink-100 px-2 py-1 text-[12px] text-ink-500">
        <button
          type="button"
          aria-label="Ask AI"
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-ink-500 hover:bg-ink-100"
        >
          <span className="text-brand-500">✦</span> Improve description
        </button>
        <span className="mx-1 h-4 w-px bg-ink-200" aria-hidden />
        <ToolbarButton label="Text style">T<sub>t</sub></ToolbarButton>
        <ToolbarButton label="Bold">B</ToolbarButton>
        <ToolbarButton label="More format">∨</ToolbarButton>
        <ToolbarButton label="Bullet list">•</ToolbarButton>
        <ToolbarButton label="Color">A</ToolbarButton>
        <ToolbarButton label="Insert">@</ToolbarButton>
        <ToolbarButton label="Code">{`</>`}</ToolbarButton>
        <ToolbarButton label="Insert link">+</ToolbarButton>
        <ToolbarButton label="Attach">📎</ToolbarButton>
        <span className="ml-auto" />
        <ToolbarButton label="Undo">↶</ToolbarButton>
        <ToolbarButton label="Redo">↷</ToolbarButton>
      </div>
      <MentionTextarea
        value={value}
        onChange={onChange}
        users={users}
        rows={4}
        className="w-full resize-y rounded-b border-0 px-3 py-2 text-[13px] focus:outline-none"
        placeholder="Type /ai to Ask Rovo or @ to mention and notify someone."
      />
    </div>
  );
}

function ToolbarButton({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className="inline-flex h-6 w-6 items-center justify-center rounded text-[11px] hover:bg-ink-100"
    >
      {children}
    </button>
  );
}
