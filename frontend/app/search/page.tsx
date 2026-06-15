"use client";

import { Save, Search as SearchIcon } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Avatar } from "@/components/Avatar";
import { IssueTypeIcon } from "@/components/IssueTypeIcon";
import { PriorityBadge } from "@/components/PriorityBadge";
import { api } from "@/lib/api";
import type { Issue, SavedFilter, User, UserMe } from "@/lib/types";

const HINTS = [
  'project = SCRUM',
  'status = "In Progress"',
  'priority in (Highest, High)',
  'assignee = currentUser()',
  'assignee = unassigned()',
  'labels = "regression"',
  'text ~ "deploy"',
  'created >= -7d',
  'ORDER BY priority DESC, created ASC',
];

export default function SearchPage() {
  const router = useRouter();
  const params = useSearchParams();
  const urlJql = params.get("jql") || "";
  const urlName = params.get("name") || "";

  const [jql, setJql] = useState(urlJql);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<Issue[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<SavedFilter[]>([]);
  const [users, setUsers] = useState<Record<string, User>>({});
  const [saving, setSaving] = useState(false);
  const [saveName, setSaveName] = useState(urlName);
  const [me, setMe] = useState<UserMe | null>(null);

  // Static reference data: load once.
  useEffect(() => {
    api.filters().then(setFilters).catch(() => {});
    api
      .users()
      .then((list) => {
        const m: Record<string, User> = {};
        list.forEach((u) => (m[u.id] = u));
        setUsers(m);
      })
      .catch(() => {});
    api.me().then(setMe).catch(() => {});
  }, []);

  // Whenever the URL's ?jql= or ?name= changes (sidebar click, top-bar search,
  // back/forward navigation), sync the local state and re-run the query.
  // Without this the page only honored URL params on first mount, so every
  // subsequent navigation left the textarea + results stuck on the previous
  // query and made the Run button look broken.
  useEffect(() => {
    setJql(urlJql);
    setSaveName(urlName);
    if (urlJql.trim()) {
      run(urlJql);
    } else {
      setResults(null);
      setTotal(0);
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlJql, urlName]);

  async function run(query: string) {
    setError(null);
    setRunning(true);
    try {
      const r = await api.search(query, 50, 0);
      setResults(r.issues);
      setTotal(r.total);
    } catch (e: any) {
      setError(e.message);
      setResults([]);
      setTotal(0);
    } finally {
      setRunning(false);
    }
  }

  // User clicks Run / Cmd+Enter: execute, then reflect into the URL so the
  // query is shareable / bookmarkable / back-button-friendly.
  function runFromTextarea() {
    const q = jql.trim();
    if (!q) return;
    if (q !== urlJql) {
      const qs = new URLSearchParams();
      qs.set("jql", q);
      if (saveName.trim()) qs.set("name", saveName.trim());
      router.replace(`/search?${qs.toString()}`);
      // The URL-sync effect above will pick up the change and call run().
    } else {
      run(q);
    }
  }

  async function saveFilter() {
    if (!saveName.trim() || !jql.trim()) return;
    setSaving(true);
    try {
      await api.createFilter({ name: saveName.trim(), jql, shared: true });
      const updated = await api.filters();
      setFilters(updated);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell>
      <div className="px-6 py-5">
        <header className="mb-4">
          <h1 className="text-xl font-semibold">Search</h1>
          <p className="text-sm text-ink-600 mt-0.5">
            JQL-lite. See <code className="text-[11px] bg-ink-100 px-1 rounded">docs/architecture.md</code>{" "}
            for the full grammar.
          </p>
        </header>

        <div className="rounded border border-ink-200 bg-white p-3 mb-4">
          <div className="flex gap-2">
            <textarea
              rows={2}
              value={jql}
              onChange={(e) => setJql(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  runFromTextarea();
                }
              }}
              placeholder='Try: project = SCRUM AND status = "In Progress"'
              className="flex-1 rounded border border-ink-200 px-2 py-1.5 font-mono text-sm focus:border-brand-500 focus:outline-none resize-none"
            />
            <button
              type="button"
              disabled={running || !jql.trim()}
              onClick={runFromTextarea}
              className="self-stretch rounded bg-brand-500 px-4 text-sm text-white hover:bg-brand-600 disabled:opacity-50"
              title="Run (⌘/Ctrl+Enter)"
            >
              <SearchIcon size={14} className="inline mr-1" /> Run
            </button>
          </div>

          {results && (
            <div className="mt-3 flex items-center gap-2">
              <input
                placeholder="Save as filter…"
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
                className="rounded border border-ink-200 px-2 py-1 text-sm w-60"
              />
              <button
                type="button"
                disabled={saving || !saveName.trim() || !jql.trim()}
                onClick={saveFilter}
                className="rounded border border-ink-200 px-2 py-1 text-xs hover:bg-ink-100 disabled:opacity-50"
              >
                <Save size={12} className="inline mr-1" /> Save filter
              </button>
              <span className="text-xs text-ink-500 ml-auto">{total} result{total === 1 ? "" : "s"}</span>
            </div>
          )}

          <div className="mt-3 flex flex-wrap gap-1">
            {HINTS.map((h) => (
              <button
                type="button"
                key={h}
                className="rounded border border-ink-200 bg-ink-50 px-2 py-0.5 text-[11px] font-mono text-ink-700 hover:bg-ink-100"
                onClick={() =>
                  setJql((cur) => {
                    if (!cur) return h;
                    // ORDER BY must be appended without a boolean conjunction;
                    // everything else joins with AND.
                    if (h.startsWith("ORDER BY")) {
                      const stripped = cur.replace(/\s+ORDER\s+BY\s+.*$/i, "");
                      return `${stripped.trim()} ${h}`;
                    }
                    return `${cur} AND ${h}`;
                  })
                }
              >
                {h}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="mb-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="grid grid-cols-[220px_1fr] gap-4">
          <aside className="rounded border border-ink-200 bg-white">
            <div className="px-3 py-2 border-b border-ink-200 text-[11px] font-semibold uppercase tracking-wide text-ink-700">
              Saved filters
            </div>
            <ul className="divide-y divide-ink-100">
              {filters.map((f) => {
                const isActive = f.jql === urlJql;
                return (
                  <li key={f.id}>
                    <button
                      type="button"
                      className={`w-full text-left px-3 py-2 text-sm ${
                        isActive ? "bg-brand-50" : "hover:bg-ink-50"
                      }`}
                      onClick={() => {
                        const qs = new URLSearchParams();
                        qs.set("jql", f.jql);
                        qs.set("name", f.name);
                        router.replace(`/search?${qs.toString()}`);
                      }}
                    >
                      <div className={`font-medium ${isActive ? "text-brand-700" : ""}`}>{f.name}</div>
                      <div className="text-[11px] font-mono text-ink-500 truncate">{f.jql}</div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>

          <div className="rounded border border-ink-200 bg-white overflow-hidden">
            {!results ? (
              <div className="px-3 py-6 text-sm text-ink-400 text-center">
                Run a query to see results.
              </div>
            ) : results.length === 0 ? (
              <EmptyResults jql={urlJql || jql} me={me} />
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-ink-50 text-left text-[11px] font-semibold uppercase tracking-wide text-ink-600">
                    <th className="px-3 py-2 w-8"></th>
                    <th className="px-3 py-2 w-20">Key</th>
                    <th className="px-3 py-2">Summary</th>
                    <th className="px-3 py-2 w-28">Status</th>
                    <th className="px-3 py-2 w-20">Priority</th>
                    <th className="px-3 py-2 w-32">Assignee</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((i) => (
                    <tr key={i.id} className="border-t border-ink-100 hover:bg-ink-50">
                      <td className="px-3 py-1.5"><IssueTypeIcon type={i.issue_type} size={14} /></td>
                      <td className="px-3 py-1.5">
                        <Link href={`/issue?id=${i.id}`} className="font-mono text-[12px] text-brand-600 hover:underline">
                          {i.id}
                        </Link>
                      </td>
                      <td className="px-3 py-1.5">
                        <Link href={`/issue?id=${i.id}`} className="hover:underline">{i.summary}</Link>
                      </td>
                      <td className="px-3 py-1.5 text-ink-700">{i.status || "—"}</td>
                      <td className="px-3 py-1.5">
                        <span className="inline-flex items-center gap-1">
                          <PriorityBadge priority={i.priority} size={12} />
                          <span className="text-[12px] text-ink-700">{i.priority}</span>
                        </span>
                      </td>
                      <td className="px-3 py-1.5">
                        {i.owner ? (
                          <span className="inline-flex items-center gap-1.5">
                            <Avatar
                              name={users[i.owner]?.name}
                              color={users[i.owner]?.avatar_color}
                              size={20}
                            />
                            <span className="text-[12px]">{users[i.owner]?.name || i.owner}</span>
                          </span>
                        ) : (
                          <span className="text-ink-400">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}

function EmptyResults({ jql, me }: { jql: string; me: UserMe | null }) {
  // `currentUser()` filters are inherently identity-scoped. If a user lands on
  // one and gets 0 results, the actionable explanation is usually "this query
  // is *about you*, not the data" — not "JQL is broken".
  const usesCurrentUser = /currentUser\s*\(\s*\)/i.test(jql);
  return (
    <div className="px-6 py-10 text-center">
      <div className="text-sm font-medium text-ink-700 mb-1">No issues match this query.</div>
      <div className="text-[12px] text-ink-500">
        {usesCurrentUser && me ? (
          <>
            This query filters by <code className="bg-ink-100 px-1 rounded">currentUser()</code>{" "}
            — you're signed in as <span className="font-medium">{me.name}</span>. Try removing
            the <code className="bg-ink-100 px-1 rounded">assignee = currentUser()</code> clause
            to see all matching issues, or sign in as a different user.
          </>
        ) : (
          <>Try widening the query (drop a clause) or check the saved filters on the left.</>
        )}
      </div>
    </div>
  );
}
