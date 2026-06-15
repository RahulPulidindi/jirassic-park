"use client";

import {
  Bell,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Filter as FilterIcon,
  Grid2x2,
  HelpCircle,
  LayoutGrid,
  Plus,
  Search,
  Settings,
  Star,
  User as UserIcon,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api, clearToken } from "@/lib/api";
import { TESTID } from "@/lib/jira-testids";
import type { Activity, Issue, Project, SavedFilter, User } from "@/lib/types";
import { cn, relativeTime, setEnvClockOffset } from "@/lib/utils";

import { Avatar } from "./Avatar";
import { CreateIssueModal } from "./CreateIssueModal";
import { IssueTypeIcon } from "./IssueTypeIcon";

// Project key + number ("PLAT-60"). Used by the global search to short-circuit
// straight to the issue page when the user types a key Jira-style.
const ISSUE_KEY_RE = /^([A-Z][A-Z0-9_]{1,15})-(\d+)$/i;

/**
 * Two-pane shell modeled on Jira's current layout:
 *
 *  +-----------------------------------------------------------+
 *  | bento | JP | -- search ---- | + Create  bell  ? gear  AV |
 *  +-------+---------------------------------------------------+
 *  | sidebar |                                                 |
 *  |  For you|                                                 |
 *  |  ...    |              page content                       |
 *  +---------+--------------------------------------------------+
 *
 * Sidebar groupings mirror the screenshot (For you / Recent / Starred /
 * Projects / Filters / More) so reviewers familiar with Jira find their way
 * around without thinking.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [me, setMe] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [filters, setFilters] = useState<SavedFilter[]>([]);
  const [mentions, setMentions] = useState<Activity[]>([]);
  const [bellOpen, setBellOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const bellRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    api
      .me()
      .then(setMe)
      .catch(() => router.push("/login"));
    api.projects().then(setProjects).catch(() => {});
    api.filters().then(setFilters).catch(() => {});
    api.myMentions(20).then(setMentions).catch(() => {});
    // Align the frontend's notion of "now" with the env clock so frozen /
    // advanced runs display "2h ago" relative to the env's clock, not the
    // browser's wall clock.
    api
      .clock()
      .then((c) => setEnvClockOffset(c.now))
      .catch(() => setEnvClockOffset(null));
  }, [router]);

  // Poll mentions every 20s so the bell badge feels alive in long-lived tabs.
  useEffect(() => {
    const t = setInterval(() => {
      api.myMentions(20).then(setMentions).catch(() => {});
    }, 20000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (target?.tagName === "INPUT" || target?.tagName === "TEXTAREA") return;
      if (e.key === "/") {
        e.preventDefault();
        router.push("/search");
      }
      if (e.key === "c" && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        setCreateOpen(true);
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [router]);

  useEffect(() => {
    if (!bellOpen) return;
    function onDoc(e: MouseEvent) {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) {
        setBellOpen(false);
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [bellOpen]);

  const unreadCount = mentions.length;

  return (
    <div
      className="grid h-screen grid-cols-[244px_1fr] grid-rows-[56px_1fr] bg-ink-50"
      data-testid={TESTID.appShell}
    >
      <TopBar
        me={me}
        unreadCount={unreadCount}
        bellRef={bellRef}
        bellOpen={bellOpen}
        setBellOpen={setBellOpen}
        mentions={mentions}
        onCreate={() => setCreateOpen(true)}
      />

      <Sidebar projects={projects} filters={filters} me={me} />

      <main className="min-w-0 min-h-0 overflow-y-auto scrollbar-thin">
        {children}
      </main>

      {createOpen && (
        <CreateIssueModal
          projects={projects}
          me={me}
          onClose={() => setCreateOpen(false)}
        />
      )}
    </div>
  );
}

// ----- Top bar ------------------------------------------------------------

function TopBar({
  me,
  unreadCount,
  bellRef,
  bellOpen,
  setBellOpen,
  mentions,
  onCreate,
}: {
  me: User | null;
  unreadCount: number;
  bellRef: React.RefObject<HTMLDivElement>;
  bellOpen: boolean;
  setBellOpen: (open: boolean) => void;
  mentions: Activity[];
  onCreate: () => void;
}) {
  const router = useRouter();
  return (
    <header
      className="col-span-2 flex items-center justify-between border-b border-ink-200 bg-white px-3"
      data-testid={TESTID.topNav.container}
      role="banner"
    >
      <div className="flex items-center gap-2">
        <IconButton aria-label="App switcher" testid={TESTID.topNav.appSwitcher}>
          <Grid2x2 size={18} className="text-ink-500" />
        </IconButton>
        <Link
          href="/"
          className="flex items-center gap-2 font-semibold text-ink-800"
          data-testid={TESTID.topNav.productHome}
          aria-label="Jirassic Park home"
        >
          <span className="rounded bg-brand-500 px-1.5 py-0.5 text-[12px] font-bold tracking-tight text-white">
            JP
          </span>
          <span className="text-[14px]">Jirassic Park</span>
        </Link>
      </div>

      <div className="flex flex-1 justify-center px-6">
        <SearchBox />
      </div>

      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onCreate}
          data-testid={TESTID.topNav.create}
          aria-label="Create issue"
          className="mr-1 inline-flex items-center gap-1 rounded bg-brand-500 px-3 py-1.5 text-[13px] font-medium text-white hover:bg-brand-600"
          title="Create issue (c)"
        >
          <Plus size={14} aria-hidden />
          Create
        </button>
        <div ref={bellRef} className="relative">
          <IconButton
            aria-label="Notifications"
            testid={TESTID.topNav.notifications}
            onClick={() => setBellOpen(!bellOpen)}
            active={bellOpen}
          >
            <Bell size={16} className="text-ink-600" />
            {unreadCount > 0 && (
              <span
                aria-label={`${unreadCount} unread notifications`}
                className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium text-white"
              >
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </IconButton>
          {bellOpen && <NotificationsPanel mentions={mentions} />}
        </div>
        <IconButton aria-label="Help" testid={TESTID.topNav.help}>
          <HelpCircle size={16} className="text-ink-600" />
        </IconButton>
        <IconButton aria-label="Settings" testid={TESTID.topNav.settings}>
          <Settings size={16} className="text-ink-600" />
        </IconButton>
        {me && (
          <button
            type="button"
            data-testid={TESTID.topNav.profile}
            aria-label={`Account menu for ${me.name}`}
            className="ml-1 rounded p-0.5 hover:ring-2 hover:ring-brand-100"
            title={`${me.name} (${me.role}) — click to log out`}
            onClick={() => {
              clearToken();
              router.push("/login");
            }}
          >
            <Avatar name={me.name} color={me.avatar_color} size={28} />
          </button>
        )}
      </div>
    </header>
  );
}

function IconButton({
  children,
  active,
  testid,
  ...rest
}: {
  children: React.ReactNode;
  active?: boolean;
  testid?: string;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      data-testid={testid}
      className={cn(
        "relative inline-flex h-8 w-8 items-center justify-center rounded hover:bg-ink-100",
        active && "bg-ink-100",
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

/**
 * Global quick-search.
 *
 * Behavior chosen to match the user expectations the screenshots flagged:
 *
 * 1. Typing a project key like `PLAT-60` (with optional hyphen/number) jumps
 *    directly to that issue on Enter, the same way Jira's quicksearch does.
 * 2. Otherwise typing pops a dropdown of matching issues (debounced
 *    `text ~ "..."` against the API), with arrow-key navigation. Enter on a
 *    highlighted result opens that issue.
 * 3. Enter with no selection (and no exact key match) falls back to the full
 *    /search page with the user's query as the JQL.
 *
 * This makes the bar useful as an issue-locator, not just a redirect to the
 * advanced-search page.
 */
function SearchBox() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<Issue[]>([]);
  const [loading, setLoading] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Debounced fetch. We over-fetch slightly (8 rows) so the dropdown isn't
  // visually choppy when results arrive after the initial keystroke burst.
  useEffect(() => {
    const q = value.trim();
    if (!q) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const handle = window.setTimeout(async () => {
      try {
        // `text ~` searches id/summary/description/comments, so a key like
        // "PLAT-60" or a partial word like "deploy" both surface useful hits.
        const r = await api.search(`text ~ "${q.replace(/"/g, '\\"')}"`, 8, 0);
        setResults(r.issues);
        setHighlight(0);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 180);
    return () => window.clearTimeout(handle);
  }, [value]);

  // Close on outside click. Mirrors the notifications panel pattern.
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  function gotoIssue(id: string) {
    setOpen(false);
    setValue("");
    router.push(`/issue?id=${encodeURIComponent(id)}`);
  }

  function submit(e?: React.FormEvent) {
    e?.preventDefault();
    const q = value.trim();
    if (!q) {
      router.push("/search");
      setOpen(false);
      return;
    }
    // 1) Exact issue-key shortcut.
    const m = q.match(ISSUE_KEY_RE);
    if (m) {
      gotoIssue(`${m[1].toUpperCase()}-${m[2]}`);
      return;
    }
    // 2) A highlighted suggestion wins over a fresh search.
    if (open && results.length > 0) {
      gotoIssue(results[highlight]?.id ?? results[0].id);
      return;
    }
    // 3) Fall through to the full search page.
    router.push(`/search?jql=${encodeURIComponent(`text ~ "${q}"`)}`);
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) setOpen(true);
      setHighlight((h) => Math.min(h + 1, Math.max(results.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    }
  }

  const trimmed = value.trim();
  const keyMatch = trimmed.match(ISSUE_KEY_RE);

  return (
    <div
      ref={containerRef}
      className="relative w-full max-w-[520px]"
      data-testid={TESTID.topNav.search.container}
      role="search"
    >
      <form onSubmit={submit} role="search" aria-label="Quick search">
        <div
          className={cn(
            "flex items-center gap-2 rounded border border-ink-200 bg-white px-2.5 py-1",
            "focus-within:border-brand-500 focus-within:ring-1 focus-within:ring-brand-100",
          )}
        >
          <Search size={14} className="text-ink-400" aria-hidden />
          <input
            ref={inputRef}
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              setOpen(true);
            }}
            onFocus={() => trimmed && setOpen(true)}
            onKeyDown={onKeyDown}
            placeholder="Search issues, summaries, comments — or paste a key like PLAT-60"
            aria-label="Search issues"
            aria-expanded={open}
            aria-haspopup="listbox"
            aria-controls="quick-search-results"
            role="combobox"
            data-testid={TESTID.topNav.search.input}
            className="w-full bg-transparent text-[13px] focus:outline-none"
            autoComplete="off"
            spellCheck={false}
          />
          <kbd
            data-testid={TESTID.topNav.search.keyShortcut}
            className="rounded bg-ink-100 px-1 font-mono text-[10px] text-ink-500"
          >
            /
          </kbd>
        </div>
      </form>

      {open && trimmed.length > 0 && (
        <div
          id="quick-search-results"
          role="listbox"
          aria-label="Search results"
          className="absolute left-0 right-0 top-9 z-30 max-h-[420px] overflow-y-auto rounded border border-ink-200 bg-white shadow-pop scrollbar-thin"
        >
          {keyMatch && (
            <button
              type="button"
              role="option"
              aria-selected={false}
              onMouseDown={(e) => {
                e.preventDefault();
                gotoIssue(`${keyMatch[1].toUpperCase()}-${keyMatch[2]}`);
              }}
              data-testid={TESTID.topNav.search.result(`${keyMatch[1].toUpperCase()}-${keyMatch[2]}`)}
              className="flex w-full items-center gap-2 border-b border-ink-100 px-3 py-2 text-left text-[12px] hover:bg-ink-50"
            >
              <kbd className="rounded bg-ink-100 px-1 font-mono text-[10px] text-ink-500">↵</kbd>
              <span>
                Open issue{" "}
                <span className="font-mono text-brand-600">
                  {keyMatch[1].toUpperCase()}-{keyMatch[2]}
                </span>
              </span>
            </button>
          )}
          {loading && results.length === 0 && (
            <div className="px-3 py-2 text-[12px] text-ink-500">Searching…</div>
          )}
          {!loading && results.length === 0 && !keyMatch && (
            <div className="px-3 py-2 text-[12px] text-ink-500">
              No issues mention <span className="font-mono">{trimmed}</span>.
            </div>
          )}
          {results.map((i, idx) => (
            <button
              key={i.id}
              type="button"
              role="option"
              aria-selected={idx === highlight}
              data-testid={TESTID.topNav.search.result(i.id)}
              onMouseDown={(e) => {
                e.preventDefault();
                gotoIssue(i.id);
              }}
              onMouseEnter={() => setHighlight(idx)}
              className={cn(
                "flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px]",
                idx === highlight ? "bg-brand-50" : "hover:bg-ink-50",
              )}
            >
              <IssueTypeIcon type={i.issue_type} size={13} />
              <span className="font-mono text-[11px] text-brand-600">{i.id}</span>
              <span className="truncate text-ink-800">{i.summary}</span>
              <span className="ml-auto shrink-0 text-[10px] text-ink-500">{i.status || ""}</span>
            </button>
          ))}
          {results.length > 0 && (
            <button
              type="button"
              data-testid={TESTID.topNav.search.seeAll}
              onMouseDown={(e) => {
                e.preventDefault();
                setOpen(false);
                router.push(`/search?jql=${encodeURIComponent(`text ~ "${trimmed}"`)}`);
                setValue("");
              }}
              className="flex w-full items-center gap-2 border-t border-ink-100 px-3 py-2 text-left text-[12px] text-ink-600 hover:bg-ink-50"
            >
              <Search size={12} />
              <span>
                Search all issues for <span className="font-mono">{trimmed}</span>
              </span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function NotificationsPanel({ mentions }: { mentions: Activity[] }) {
  return (
    <div className="absolute right-0 top-10 z-30 w-[360px] rounded border border-ink-200 bg-white shadow-pop">
      <div className="flex items-center justify-between border-b border-ink-200 px-3 py-2">
        <span className="text-[13px] font-semibold text-ink-800">Notifications</span>
        <span className="text-[11px] text-ink-500">
          {mentions.length} {mentions.length === 1 ? "mention" : "mentions"}
        </span>
      </div>
      <div className="max-h-[420px] overflow-y-auto scrollbar-thin">
        {mentions.length === 0 ? (
          <div className="px-3 py-8 text-center text-[12px] text-ink-500">
            No new mentions. You'll see <code>@you</code> here.
          </div>
        ) : (
          mentions.map((m) => (
            <Link
              key={m.id}
              href={`/issue?id=${m.issue_id}`}
              className="block border-b border-ink-100 px-3 py-2 last:border-b-0 hover:bg-ink-50"
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[12px] font-medium text-ink-800">
                  Mentioned in <span className="font-mono">{m.issue_id}</span>
                </span>
                <span className="text-[11px] text-ink-400">
                  {relativeTime(m.created_at)}
                </span>
              </div>
              {m.comment_body && (
                <div className="mt-0.5 line-clamp-2 text-[12px] text-ink-600">
                  {m.comment_body}
                </div>
              )}
            </Link>
          ))
        )}
      </div>
    </div>
  );
}

// ----- Sidebar ------------------------------------------------------------

function Sidebar({
  projects,
  filters,
  me,
}: {
  projects: Project[];
  filters: SavedFilter[];
  me: User | null;
}) {
  const isAdmin = me?.role === "admin";
  // We don't have a real "starred" feature yet; the first three projects act as
  // the user's pinned set. This matches Jira's pattern where Starred is the
  // primary navigation aid and the full project list lives one level deeper.
  const starred = projects.slice(0, 3);

  return (
    <aside
      className="flex flex-col border-r border-ink-200 bg-white py-2 text-[13px]"
      data-testid={TESTID.sidebar.container}
      aria-label="Project navigation"
    >
      <nav className="flex-1 overflow-y-auto px-2 scrollbar-thin" aria-label="Sidebar">
        <SidebarItem href="/" icon={<Star size={14} />}>
          For you
        </SidebarItem>
        <SidebarItem
          href={"/search?jql=" + encodeURIComponent("ORDER BY updated DESC")}
          icon={<Search size={14} />}
        >
          Recent
        </SidebarItem>
        <SidebarItem href="/projects" icon={<LayoutGrid size={14} />}>
          Projects
        </SidebarItem>

        <SidebarSectionLabel>Starred</SidebarSectionLabel>
        {starred.map((p) => (
          <ProjectSidebarItem key={p.key} project={p} />
        ))}

        <SidebarSectionLabel>Filters</SidebarSectionLabel>
        {filters.slice(0, 6).map((f) => (
          <SidebarItem
            key={f.id}
            href={`/search?jql=${encodeURIComponent(f.jql)}&name=${encodeURIComponent(f.name)}`}
            icon={<FilterIcon size={14} />}
          >
            <span className="truncate">{f.name}</span>
          </SidebarItem>
        ))}

        {isAdmin && (
          <>
            <SidebarSectionLabel>More</SidebarSectionLabel>
            <SidebarItem href="/admin/users" icon={<Users size={14} />}>
              Users
            </SidebarItem>
          </>
        )}
      </nav>

      <div className="border-t border-ink-200 px-3 pt-2 pb-1 text-[11px] text-ink-500">
        <Link href="/projects" className="inline-flex items-center gap-1 hover:text-ink-700">
          <CircleHelp size={12} />
          Get help with navigation
        </Link>
      </div>
    </aside>
  );
}

function SidebarSectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-3 mb-0.5 px-2 text-[11px] font-semibold uppercase tracking-wider text-ink-500">
      {children}
    </div>
  );
}

function SidebarItem({
  href,
  icon,
  children,
  indent = 0,
}: {
  href: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  indent?: number;
}) {
  const pathname = usePathname();
  const sp = useSearchParams();

  // A link is "active" only when its path AND every query param it declares
  // also match the current URL. Without this, `/search?jql=...` and
  // `/board?key=DEBT` would light up every sibling on the same path.
  const [linkPath, linkQuery] = href.split("?");
  let active = pathname === linkPath;
  if (active && linkQuery) {
    const expected = new URLSearchParams(linkQuery);
    for (const [k, v] of expected.entries()) {
      if (sp?.get(k) !== v) {
        active = false;
        break;
      }
    }
  }
  return (
    <Link
      href={href}
      className={cn(
        "group flex items-center gap-2 rounded px-2 py-1 text-ink-700 hover:bg-ink-100",
        active && "bg-brand-50 text-brand-600 hover:bg-brand-50",
      )}
      style={{ paddingLeft: 8 + indent * 12 }}
    >
      {icon && (
        <span className={cn("text-ink-500", active && "text-brand-500")}>{icon}</span>
      )}
      <span className="flex-1 truncate">{children}</span>
    </Link>
  );
}

function ProjectSidebarItem({ project }: { project: Project }) {
  const [open, setOpen] = useState(true);
  const sp = useSearchParams();
  const pathname = usePathname();
  const isActiveBoard =
    pathname === "/board" && sp?.get("key") === project.key;
  return (
    <div>
      <div
        className={cn(
          "group flex items-center gap-1 rounded px-1 py-1 hover:bg-ink-100",
          isActiveBoard && "bg-brand-50",
        )}
      >
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="rounded p-0.5 text-ink-400 hover:bg-ink-200/60"
          aria-label={open ? "Collapse" : "Expand"}
        >
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </button>
        <Link
          href={`/board?key=${project.key}`}
          className={cn(
            "flex flex-1 items-center gap-2 truncate text-ink-700",
            isActiveBoard && "text-brand-600",
          )}
        >
          <span
            className="inline-block h-3.5 w-3.5 shrink-0 rounded-sm"
            style={{ backgroundColor: project.avatar_color }}
          />
          <span className="truncate">{project.name}</span>
        </Link>
      </div>
      {open && (
        <div className="mb-1">
          <SidebarItem
            href={`/board?key=${project.key}`}
            indent={1}
            icon={<LayoutGrid size={12} />}
          >
            Board
          </SidebarItem>
          <SidebarItem
            href={`/backlog?key=${project.key}`}
            indent={1}
            icon={<LayoutGrid size={12} />}
          >
            Backlog
          </SidebarItem>
          <SidebarItem
            href={`/settings?key=${project.key}`}
            indent={1}
            icon={<Settings size={12} />}
          >
            Settings
          </SidebarItem>
        </div>
      )}
    </div>
  );
}

// (CreateIssueModal moved to components/CreateIssueModal.tsx so the modal can
// be tested independently and so AppShell stays focused on layout/navigation.)
