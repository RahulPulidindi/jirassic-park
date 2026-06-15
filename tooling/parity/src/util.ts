/**
 * Small shared helpers used across capture, tracing, and the orchestrator.
 */
import type { Page } from "playwright";

import { extractSkeletonInPage, signatures, type SkelNode } from "./normalizer.ts";

/**
 * tsx/esbuild wraps named functions with a `__name(...)` helper that exists in
 * Node but not the browser. Anything we hand to `page.evaluate` is stringified
 * and run in the page, so define a no-op `__name` in that world first.
 */
const NAME_SHIM = "window.__name = window.__name || function (f) { return f; };";

/** Click the first match of several candidate selectors; throw if none work. */
export async function clickAny(page: Page, selectors: string[], timeout = 8000): Promise<void> {
  for (const sel of selectors) {
    const loc = page.locator(sel).first();
    try {
      await loc.waitFor({ state: "visible", timeout });
      await loc.click();
      return;
    } catch {
      /* try next */
    }
  }
  throw new Error(`None of the candidate selectors were clickable: ${selectors.join(", ")}`);
}

/** Fill the first match of several candidate selectors; throw if none work. */
export async function fillAny(page: Page, selectors: string[], value: string, timeout = 8000): Promise<void> {
  for (const sel of selectors) {
    const loc = page.locator(sel).first();
    try {
      await loc.waitFor({ state: "visible", timeout });
      await loc.fill(value);
      return;
    } catch {
      /* try next */
    }
  }
  throw new Error(`None of the candidate selectors were fillable: ${selectors.join(", ")}`);
}

/** Extract the normalized skeleton of a subtree from inside the page. */
export async function snapshotSkeleton(page: Page, selector: string): Promise<SkelNode | null> {
  await page.evaluate(NAME_SHIM);
  return (await page.evaluate(extractSkeletonInPage, selector)) as SkelNode | null;
}

/** Field/affordance signatures of a subtree — the agent-relevant identities. */
export async function snapshotSignatures(page: Page, selector: string): Promise<string[]> {
  return signatures(await snapshotSkeleton(page, selector));
}

/** What appeared / disappeared between two signature multisets. */
export function multisetDelta(before: string[], after: string[]): { appeared: string[]; disappeared: string[] } {
  const count = (xs: string[]) => {
    const m = new Map<string, number>();
    for (const x of xs) m.set(x, (m.get(x) ?? 0) + 1);
    return m;
  };
  const a = count(before);
  const b = count(after);
  const keys = new Set([...a.keys(), ...b.keys()]);
  const appeared: string[] = [];
  const disappeared: string[] = [];
  for (const k of keys) {
    const ca = a.get(k) ?? 0;
    const cb = b.get(k) ?? 0;
    if (cb > ca) for (let i = 0; i < cb - ca; i++) appeared.push(k);
    if (ca > cb) for (let i = 0; i < ca - cb; i++) disappeared.push(k);
  }
  appeared.sort();
  disappeared.sort();
  return { appeared, disappeared };
}

/** Settle late XHRs + rendering without hanging on Jira's long-poll sockets. */
export async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(1200);
}
