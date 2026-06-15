"use client";

import { cn, userInitials } from "@/lib/utils";

export function Avatar({
  name,
  color,
  size = 24,
  className,
}: {
  name?: string | null;
  color?: string | null;
  size?: number;
  className?: string;
}) {
  if (!name) {
    return (
      <span
        className={cn(
          "inline-flex items-center justify-center rounded-full border border-dashed border-ink-300 text-ink-400",
          className,
        )}
        style={{ width: size, height: size, fontSize: size * 0.45 }}
        title="Unassigned"
      >
        ?
      </span>
    );
  }
  return (
    <span
      className={cn("inline-flex items-center justify-center rounded-full text-white font-medium", className)}
      style={{
        width: size,
        height: size,
        backgroundColor: color || "#5d6a99",
        fontSize: size * 0.42,
      }}
      title={name}
    >
      {userInitials(name)}
    </span>
  );
}
