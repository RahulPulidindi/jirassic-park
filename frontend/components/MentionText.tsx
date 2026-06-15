"use client";

/**
 * Read-only renderer: shows a markdown-y string with `@user_*` / `@first_last`
 * tokens upgraded to brand-blue chips. The split is done client-side from the
 * raw body (rather than `comment.mentions`) so the visual highlight tracks the
 * text exactly even if a future edit changes who was tagged.
 */

import Link from "next/link";
import { useMemo } from "react";

import type { User } from "@/lib/types";

type Segment =
  | { kind: "text"; text: string }
  | { kind: "mention"; user: User };

const MENTION_RE = /(?<![A-Za-z0-9_])@([A-Za-z][A-Za-z0-9_.\-]{0,40})/g;

export function splitMentions(body: string, users: User[]): Segment[] {
  if (!body || !users.length) return [{ kind: "text", text: body }];
  const byId = new Map(users.map((u) => [u.id, u]));
  const bySuffix = new Map(users.map((u) => [u.id.replace(/^user_/, ""), u]));
  const out: Segment[] = [];
  let lastIdx = 0;
  let m: RegExpExecArray | null;
  // Reset stateful regex.
  MENTION_RE.lastIndex = 0;
  while ((m = MENTION_RE.exec(body))) {
    const raw = m[1].replace(/[.,;:!?]+$/, "");
    const normalized = raw.toLowerCase().replace(/[-.]/g, "_");
    const user = byId.get(raw) || bySuffix.get(normalized);
    if (!user) continue;
    if (m.index > lastIdx) {
      out.push({ kind: "text", text: body.slice(lastIdx, m.index) });
    }
    out.push({ kind: "mention", user });
    lastIdx = m.index + 1 + raw.length;
  }
  if (lastIdx < body.length) {
    out.push({ kind: "text", text: body.slice(lastIdx) });
  }
  return out.length ? out : [{ kind: "text", text: body }];
}

export function MentionText({
  body,
  users,
  className,
}: {
  body: string;
  users: User[];
  className?: string;
}) {
  const parts = useMemo(() => splitMentions(body, users), [body, users]);
  return (
    <div className={className}>
      {parts.map((p, i) =>
        p.kind === "mention" ? (
          <Link
            key={i}
            href={`/search?jql=${encodeURIComponent(
              `assignee = ${p.user.id} OR reporter = ${p.user.id}`,
            )}`}
            className="rounded bg-brand-50 px-1 font-medium text-brand-600 hover:underline"
            title={p.user.name}
          >
            @{p.user.name}
          </Link>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </div>
  );
}
