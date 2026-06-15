"use client";

/**
 * A textarea with Jira-style `@mention` autocomplete.
 *
 * Why a dedicated component:
 * - The user has to be able to fluently @-tag a teammate while typing, the
 *   way they would in real Jira. A plain <textarea> with a regex-on-submit
 *   silently swallows typos like `@priya_iyer` -> `@priya` (no match).
 * - This component intercepts `@<prefix>`, surfaces a live filtered list,
 *   and on selection rewrites the buffer to the canonical handle so the
 *   backend mention parser always finds the user.
 *
 * The component is uncontrolled w.r.t. the popover state (it owns it) and
 * controlled w.r.t. text (value/onChange) so callers can submit it like any
 * other input.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import type { User } from "@/lib/types";
import { cn } from "@/lib/utils";

import { Avatar } from "./Avatar";

export interface MentionTextareaProps
  extends Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, "onChange" | "value"> {
  value: string;
  onChange: (next: string) => void;
  users: User[];
  /** Optional keyboard handler. We call this AFTER our own handling. */
  onKeyDownExtra?: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
}

interface PickerState {
  start: number;        // index of the '@' in value
  query: string;        // characters typed after '@'
  caret: { top: number; left: number }; // pixel coordinates of the cursor
  highlighted: number;  // index into the filtered candidate list
}

const MAX_RESULTS = 6;

export function MentionTextarea({
  value,
  onChange,
  users,
  onKeyDownExtra,
  className,
  ...rest
}: MentionTextareaProps) {
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const mirrorRef = useRef<HTMLDivElement | null>(null);
  const [picker, setPicker] = useState<PickerState | null>(null);

  // Filtered candidates for the current query. We match BOTH the canonical
  // handle (`priya_iyer`) and the human name (`Priya Iyer`) so typing `@pri`
  // or `@Priya` both surface the same person.
  const candidates = useMemo(() => {
    if (!picker) return [];
    const q = picker.query.toLowerCase();
    const scored: { user: User; score: number }[] = [];
    for (const u of users) {
      const handle = u.id.replace(/^user_/, "").toLowerCase();
      const name = u.name.toLowerCase();
      let score = 0;
      if (handle.startsWith(q)) score = 4;
      else if (name.startsWith(q)) score = 3;
      else if (handle.includes(q)) score = 2;
      else if (name.includes(q)) score = 1;
      if (score > 0 || q === "") scored.push({ user: u, score });
    }
    scored.sort((a, b) => b.score - a.score || a.user.name.localeCompare(b.user.name));
    return scored.slice(0, MAX_RESULTS).map((s) => s.user);
  }, [picker, users]);

  // Detect `@<prefix>` immediately preceding the caret. The regex requires a
  // word boundary before `@` so an email like `foo@example.com` doesn't open
  // the picker.
  function refreshPicker(text: string, caretPos: number) {
    const upToCaret = text.slice(0, caretPos);
    const m = upToCaret.match(/(?:^|[^\w])(@([A-Za-z0-9_.\-]*))$/);
    if (!m) {
      setPicker(null);
      return;
    }
    const atIdx = caretPos - m[1].length;
    const query = m[2];
    const coords = caretCoords(taRef.current, mirrorRef.current, caretPos);
    setPicker({ start: atIdx, query, caret: coords, highlighted: 0 });
  }

  function commitMention(user: User) {
    if (!picker || !taRef.current) return;
    const ta = taRef.current;
    const before = value.slice(0, picker.start);
    const afterStart = picker.start + 1 + picker.query.length;
    const after = value.slice(afterStart);
    const handle = user.id.replace(/^user_/, "");
    const inserted = `@${handle} `;
    const next = before + inserted + after;
    onChange(next);
    setPicker(null);
    // Restore focus + place caret after the inserted handle.
    requestAnimationFrame(() => {
      const pos = (before + inserted).length;
      ta.focus();
      ta.setSelectionRange(pos, pos);
    });
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (picker && candidates.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setPicker({
          ...picker,
          highlighted: (picker.highlighted + 1) % candidates.length,
        });
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setPicker({
          ...picker,
          highlighted:
            (picker.highlighted - 1 + candidates.length) % candidates.length,
        });
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        commitMention(candidates[picker.highlighted]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setPicker(null);
        return;
      }
    }
    onKeyDownExtra?.(e);
  }

  function onTextChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const next = e.target.value;
    onChange(next);
    refreshPicker(next, e.target.selectionStart ?? next.length);
  }

  function onSelectOrClick() {
    const ta = taRef.current;
    if (!ta) return;
    refreshPicker(ta.value, ta.selectionStart ?? ta.value.length);
  }

  return (
    <div className="relative">
      <textarea
        {...rest}
        ref={taRef}
        value={value}
        onChange={onTextChange}
        onKeyDown={onKeyDown}
        onClick={onSelectOrClick}
        onKeyUp={onSelectOrClick}
        className={className}
      />
      {/* Invisible mirror for caret coordinate measurement. */}
      <div
        ref={mirrorRef}
        aria-hidden
        className="pointer-events-none invisible absolute left-0 top-0 whitespace-pre-wrap break-words"
      />
      {picker && candidates.length > 0 && (
        <ul
          className="absolute z-30 max-h-[220px] w-[260px] overflow-y-auto rounded border border-ink-200 bg-white py-1 text-[13px] shadow-pop"
          style={{ top: picker.caret.top + 20, left: picker.caret.left }}
        >
          {candidates.map((u, i) => (
            <li key={u.id}>
              <button
                type="button"
                onMouseDown={(e) => {
                  // Prevent the textarea from losing focus before we can rewrite it.
                  e.preventDefault();
                  commitMention(u);
                }}
                className={cn(
                  "flex w-full items-center gap-2 px-2 py-1 text-left hover:bg-brand-50",
                  i === picker.highlighted && "bg-brand-50",
                )}
              >
                <Avatar name={u.name} color={u.avatar_color} size={20} />
                <span className="flex-1 truncate text-ink-800">{u.name}</span>
                <span className="font-mono text-[11px] text-ink-400">
                  @{u.id.replace(/^user_/, "")}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Compute the (top, left) pixel position of the textarea's caret. We use a
 * hidden mirror div that recreates the textarea's text up to the caret and
 * read the position of a marker span at the end.
 */
function caretCoords(
  ta: HTMLTextAreaElement | null,
  mirror: HTMLDivElement | null,
  caret: number,
): { top: number; left: number } {
  if (!ta || !mirror) return { top: 0, left: 0 };
  const style = window.getComputedStyle(ta);
  // Copy relevant text rendering properties onto the mirror so the layout
  // matches the textarea (font, padding, line-height, width, ...).
  const props = [
    "boxSizing",
    "width",
    "height",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "paddingLeft",
    "borderTopWidth",
    "borderRightWidth",
    "borderBottomWidth",
    "borderLeftWidth",
    "fontFamily",
    "fontSize",
    "fontWeight",
    "fontStyle",
    "lineHeight",
    "letterSpacing",
    "textTransform",
    "tabSize",
    "whiteSpace",
    "wordBreak",
    "wordSpacing",
  ];
  for (const p of props) {
    (mirror.style as any)[p] = (style as any)[p];
  }
  mirror.style.position = "absolute";
  mirror.style.left = "-9999px";
  mirror.style.top = "0";
  mirror.style.visibility = "hidden";
  mirror.style.overflow = "hidden";

  const before = ta.value.slice(0, caret);
  mirror.textContent = before;
  const marker = document.createElement("span");
  marker.textContent = ".";
  mirror.appendChild(marker);

  const taRect = ta.getBoundingClientRect();
  const markerRect = marker.getBoundingClientRect();
  const mirrorRect = mirror.getBoundingClientRect();

  const top = markerRect.top - mirrorRect.top - ta.scrollTop;
  const left = markerRect.left - mirrorRect.left - ta.scrollLeft;
  return { top, left };
}
