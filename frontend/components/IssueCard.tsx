"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Issue, User } from "@/lib/types";

import { Avatar } from "./Avatar";
import { IssueTypeIcon } from "./IssueTypeIcon";
import { PriorityBadge } from "./PriorityBadge";

// Cached user lookup so we don't hammer /api/users for every card.
const userCache = new Map<string, User>();
let usersPromise: Promise<User[]> | null = null;

function useUsers(): Map<string, User> {
  const [users, setUsers] = useState<Map<string, User>>(userCache);
  useEffect(() => {
    if (userCache.size > 0) return;
    if (!usersPromise) usersPromise = api.users();
    usersPromise.then((list) => {
      list.forEach((u) => userCache.set(u.id, u));
      setUsers(new Map(userCache));
    });
  }, []);
  return users;
}

export function IssueCard({
  issue,
  draggable = true,
  compact = false,
}: {
  issue: Issue;
  draggable?: boolean;
  compact?: boolean;
}) {
  const users = useUsers();
  const owner = issue.owner ? users.get(issue.owner) : null;

  return (
    <Link
      href={`/issue?id=${issue.id}`}
      className="block rounded border border-ink-200 bg-white p-2.5 shadow-card hover:border-brand-500 transition-colors"
      draggable={draggable}
      onDragStart={(e) => {
        e.dataTransfer.setData("text/issue-id", issue.id);
        e.dataTransfer.effectAllowed = "move";
      }}
    >
      {/* Summary takes one or two lines; line-clamp keeps cards uniform. */}
      <div className="line-clamp-3 text-[13px] leading-snug text-ink-900">
        {issue.summary}
      </div>

      {/* Labels float under the summary like Jira. We cap at 2 + overflow chip. */}
      {!compact && issue.labels.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1 overflow-hidden">
          {issue.labels.slice(0, 2).map((l) => (
            <span
              key={l}
              className="max-w-[120px] truncate rounded bg-ink-100 px-1.5 py-0.5 text-[10px] text-ink-700"
              title={l}
            >
              {l}
            </span>
          ))}
          {issue.labels.length > 2 && (
            <span
              className="rounded bg-ink-100 px-1 py-0.5 text-[10px] text-ink-700"
              title={issue.labels.slice(2).join(", ")}
            >
              +{issue.labels.length - 2}
            </span>
          )}
        </div>
      )}

      {/* Footer: type+id on the left, priority/points/avatar on the right. */}
      <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-ink-500">
        <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
          <IssueTypeIcon type={issue.issue_type} size={14} />
          <span className="whitespace-nowrap font-mono text-[11px]">{issue.id}</span>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <PriorityBadge priority={issue.priority} size={14} />
          {issue.story_points != null && (
            <span className="inline-flex items-center justify-center rounded-full bg-ink-100 px-1.5 py-0.5 text-[10px] font-medium text-ink-700">
              {issue.story_points}
            </span>
          )}
          <Avatar name={owner?.name || null} color={owner?.avatar_color} size={20} />
        </div>
      </div>
    </Link>
  );
}
