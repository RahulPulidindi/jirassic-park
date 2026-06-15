"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/utils";

/**
 * ARIA 1.2 combobox / listbox.
 *
 * Implementation notes for DOM-driven agents:
 *
 *   <button role="combobox"
 *           aria-haspopup="listbox"
 *           aria-expanded={open}
 *           aria-controls={listboxId}
 *           aria-activedescendant={open ? optionIdAt(highlight) : undefined}>
 *           {selectedLabel}
 *   </button>
 *
 *   <ul role="listbox" id={listboxId}>
 *     <li role="option"
 *         id={optionId(value)}
 *         aria-selected={selected}>{label}</li>
 *   </ul>
 *
 * Keyboard:
 *   - Trigger: ArrowDown / Enter / Space opens, Escape closes.
 *   - Listbox: ArrowUp/Down move highlight, Home/End jump to first/last,
 *     Enter selects, Escape closes and restores focus to the trigger.
 *
 * Behavior:
 *   - Trigger gets focus back when the menu closes.
 *   - Outside click closes the menu.
 *   - When opening with no current value the highlight starts at index 0;
 *     otherwise it starts at the selected option so Enter is a no-op.
 *   - `testId` prop is required for DOM-agent stable targeting.
 *
 * Use this for short option lists (single column, no grouping). The bespoke
 * pickers (UserPicker, SprintPicker, PriorityPicker) follow the same ARIA
 * pattern by hand to support richer triggers (avatars, badges).
 */
export type DropdownOption<T extends string = string> = {
  value: T;
  label: string;
  hint?: string;
  /** Optional icon node to show before the label inside the listbox row. */
  icon?: React.ReactNode;
};

export function Dropdown<T extends string>({
  value,
  options,
  onChange,
  width,
  size = "sm",
  label,
  className,
  disabled = false,
  placeholder,
  testId,
  invalid = false,
  describedBy,
  required = false,
}: {
  value: T | null | undefined;
  options: DropdownOption<T>[];
  onChange: (v: T) => void;
  width?: number;
  size?: "xs" | "sm" | "md";
  /** Accessible name for the trigger button (used as aria-label if no
   * visible label is associated). */
  label?: string;
  className?: string;
  disabled?: boolean;
  placeholder?: string;
  /** Stable data-testid for the trigger button. Listbox derives its testid. */
  testId?: string;
  invalid?: boolean;
  describedBy?: string;
  required?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const listboxRef = useRef<HTMLUListElement | null>(null);
  const generatedId = useId();
  const listboxId = `${generatedId}-listbox`;
  const optionId = (idx: number) => `${generatedId}-option-${idx}`;

  // Outside click & Escape close.
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Sync highlight to current value when opening.
  useEffect(() => {
    if (!open) return;
    const i = options.findIndex((o) => o.value === value);
    setHighlight(i < 0 ? 0 : i);
    // Move focus into the listbox so arrow keys work without re-clicking.
    requestAnimationFrame(() => listboxRef.current?.focus());
  }, [open, value, options]);

  const current = useMemo(
    () => (value == null ? undefined : options.find((o) => o.value === value)),
    [options, value],
  );

  const sizeCls =
    size === "xs"
      ? "px-1.5 py-0.5 text-[11px]"
      : size === "md"
        ? "px-3 py-2 text-[14px]"
        : "px-2.5 py-1.5 text-[13px]";
  const menuItemCls =
    size === "xs" ? "px-2 py-1 text-[11px]" : size === "md" ? "px-3 py-2 text-[14px]" : "px-3 py-1.5 text-[13px]";

  function onTriggerKey(e: React.KeyboardEvent<HTMLButtonElement>) {
    if (disabled) return;
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setOpen(true);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      setHighlight(options.length - 1);
    }
  }

  function onMenuKey(e: React.KeyboardEvent<HTMLUListElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, options.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Home") {
      e.preventDefault();
      setHighlight(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setHighlight(options.length - 1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const opt = options[highlight];
      if (opt) {
        onChange(opt.value);
        setOpen(false);
        triggerRef.current?.focus();
      }
    } else if (e.key === "Tab") {
      // Close on Tab so focus moves naturally to the next form control.
      setOpen(false);
    }
  }

  return (
    <div ref={rootRef} className={cn("relative inline-block", className)}>
      <button
        ref={triggerRef}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-activedescendant={open ? optionId(highlight) : undefined}
        aria-label={label}
        aria-invalid={invalid || undefined}
        aria-required={required || undefined}
        aria-describedby={describedBy}
        data-testid={testId}
        disabled={disabled}
        onClick={() => !disabled && setOpen((v) => !v)}
        onKeyDown={onTriggerKey}
        className={cn(
          "inline-flex w-full items-center justify-between gap-1.5 rounded border bg-white text-left text-ink-800",
          invalid ? "border-red-500" : "border-ink-200",
          "hover:bg-ink-50 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-100",
          "disabled:cursor-not-allowed disabled:bg-ink-50 disabled:text-ink-400",
          sizeCls,
        )}
        style={width ? { width } : undefined}
      >
        <span className={cn("flex-1 truncate flex items-center gap-1.5", !current && "text-ink-400")}>
          {current?.icon}
          <span className="truncate">{current?.label ?? placeholder ?? "Select…"}</span>
        </span>
        <ChevronDown size={size === "xs" ? 11 : 14} className="shrink-0 text-ink-500" aria-hidden />
      </button>

      {open && (
        <ul
          ref={listboxRef}
          id={listboxId}
          role="listbox"
          aria-label={label}
          tabIndex={-1}
          onKeyDown={onMenuKey}
          data-testid={testId ? `${testId}.listbox` : undefined}
          className={cn(
            "absolute z-30 mt-1 max-h-[280px] overflow-y-auto rounded border border-ink-200 bg-white py-1 shadow-pop scrollbar-thin",
            "focus:outline-none",
          )}
          style={{ minWidth: width ?? "100%" }}
        >
          {options.length === 0 && (
            <li className="px-3 py-2 text-[12px] text-ink-400" role="presentation">
              No options.
            </li>
          )}
          {options.map((o, idx) => {
            const selected = o.value === value;
            const highlighted = idx === highlight;
            return (
              <li
                key={o.value}
                id={optionId(idx)}
                role="option"
                aria-selected={selected}
                data-testid={testId ? `${testId}.option.${o.value}` : undefined}
                onMouseEnter={() => setHighlight(idx)}
                onClick={() => {
                  onChange(o.value);
                  setOpen(false);
                  triggerRef.current?.focus();
                }}
                className={cn(
                  "flex w-full items-center justify-between gap-2 cursor-pointer",
                  menuItemCls,
                  highlighted ? "bg-brand-50 text-brand-700" : "text-ink-800 hover:bg-ink-50",
                  selected && "font-medium",
                )}
              >
                <span className="flex flex-1 items-center gap-2 truncate">
                  {o.icon}
                  <span className="truncate">{o.label}</span>
                </span>
                {o.hint && (
                  <span className="shrink-0 text-[11px] uppercase tracking-wide text-ink-500">
                    {o.hint}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
