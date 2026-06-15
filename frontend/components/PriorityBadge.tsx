"use client";

import { ArrowDown, ArrowUp, ChevronsDown, ChevronsUp, Minus } from "lucide-react";

import { cn, PRIORITY_COLORS } from "@/lib/utils";

const ICONS: Record<string, any> = {
  Highest: ChevronsUp,
  High: ArrowUp,
  Medium: Minus,
  Low: ArrowDown,
  Lowest: ChevronsDown,
};

export function PriorityBadge({ priority, size = 14 }: { priority: string; size?: number }) {
  const Icon = ICONS[priority] || Minus;
  return (
    <span
      className={cn("inline-flex items-center", PRIORITY_COLORS[priority] || "text-ink-400")}
      title={`Priority: ${priority}`}
    >
      <Icon size={size} />
    </span>
  );
}
