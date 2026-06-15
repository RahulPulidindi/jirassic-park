"use client";

import { Bookmark, Bug, ChevronUp, Layers, Square, SquareCheck } from "lucide-react";

import { cn } from "@/lib/utils";

const ICONS: Record<string, { Icon: any; bg: string }> = {
  Story: { Icon: Bookmark, bg: "bg-issuetype-story" },
  Task: { Icon: SquareCheck, bg: "bg-issuetype-task" },
  Bug: { Icon: Bug, bg: "bg-issuetype-bug" },
  Epic: { Icon: Layers, bg: "bg-issuetype-epic" },
  Subtask: { Icon: ChevronUp, bg: "bg-issuetype-subtask" },
};

export function IssueTypeIcon({
  type,
  size = 14,
  className,
}: {
  type: string;
  size?: number;
  className?: string;
}) {
  const entry = ICONS[type] || { Icon: Square, bg: "bg-ink-400" };
  const { Icon, bg } = entry;
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-sm text-white",
        bg,
        className,
      )}
      style={{ width: size, height: size }}
      title={type}
    >
      <Icon size={size * 0.7} />
    </span>
  );
}
