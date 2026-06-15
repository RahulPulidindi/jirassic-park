"use client";

import { cn } from "@/lib/utils";

const COLORS: Record<string, string> = {
  todo: "bg-ink-100 text-ink-700 border-ink-200",
  in_progress: "bg-brand-50 text-brand-700 border-brand-100",
  done: "bg-green-100 text-green-800 border-green-200",
};

export function StatusBadge({
  name,
  category,
  className,
}: {
  name: string;
  category?: string;
  className?: string;
}) {
  const palette = COLORS[category || ""] || COLORS.todo;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm border px-2 py-0.5 text-xs font-medium uppercase tracking-wide",
        palette,
        className,
      )}
    >
      {name}
    </span>
  );
}
