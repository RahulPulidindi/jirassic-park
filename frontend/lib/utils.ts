import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Parse a backend timestamp. The backend stores datetimes as UTC-naive (the
 * SQLAlchemy `DateTime` columns), and Pydantic serializes them as ISO strings
 * with no timezone suffix. JavaScript's `new Date(...)` interprets a naked
 * ISO string as LOCAL time, which is why every relative time was wrong by
 * exactly the user's UTC offset (e.g. "-25200s ago" in PDT, which is -7h).
 *
 * This helper appends `Z` when the string lacks any timezone marker so
 * `Date` parses it as UTC -- matching the backend's actual semantics.
 */
export function parseServerTime(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const hasTz = /Z$|[+\-]\d{2}:?\d{2}$/.test(iso);
  return new Date(hasTz ? iso : iso + "Z");
}

/**
 * Compare a server timestamp against the env's "now". When the universal
 * clock is frozen / advanced, the frontend uses that instant instead of
 * `Date.now()`, so "Updated 2h ago" stays sensible inside time-travel runs.
 */
let _envClockOffset = 0; // ms to ADD to Date.now() to get env "now"
export function setEnvClockOffset(serverNowIso: string | null): void {
  const d = parseServerTime(serverNowIso);
  if (!d) {
    _envClockOffset = 0;
    return;
  }
  _envClockOffset = d.getTime() - Date.now();
}
export function envNow(): number {
  return Date.now() + _envClockOffset;
}

export function relativeTime(iso: string): string {
  const d = parseServerTime(iso);
  if (!d) return "";
  const diff = Math.floor((envNow() - d.getTime()) / 1000);
  if (diff < 0) {
    // Future timestamp (e.g. due dates). Mirror Jira's "in 2d" phrasing.
    const future = -diff;
    if (future < 60) return `in ${future}s`;
    if (future < 3600) return `in ${Math.floor(future / 60)}m`;
    if (future < 86400) return `in ${Math.floor(future / 3600)}h`;
    if (future < 86400 * 30) return `in ${Math.floor(future / 86400)}d`;
    if (future < 86400 * 365) return `in ${Math.floor(future / (86400 * 30))}mo`;
    return `in ${Math.floor(future / (86400 * 365))}y`;
  }
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)}d ago`;
  if (diff < 86400 * 365) return `${Math.floor(diff / (86400 * 30))}mo ago`;
  return `${Math.floor(diff / (86400 * 365))}y ago`;
}

export function absoluteTime(iso: string): string {
  const d = parseServerTime(iso);
  return d ? d.toLocaleString() : "";
}

export const PRIORITY_COLORS: Record<string, string> = {
  Highest: "text-priority-highest",
  High: "text-priority-high",
  Medium: "text-priority-medium",
  Low: "text-priority-low",
  Lowest: "text-priority-lowest",
};

export const PRIORITY_RANK: Record<string, number> = {
  Highest: 5,
  High: 4,
  Medium: 3,
  Low: 2,
  Lowest: 1,
};

export const ISSUE_TYPE_COLORS: Record<string, string> = {
  Story: "bg-issuetype-story",
  Task: "bg-issuetype-task",
  Bug: "bg-issuetype-bug",
  Epic: "bg-issuetype-epic",
  Subtask: "bg-issuetype-subtask",
};

export function userInitials(name: string): string {
  return name
    .split(/\s+/)
    .map((s) => s[0]?.toUpperCase() || "")
    .slice(0, 2)
    .join("");
}
