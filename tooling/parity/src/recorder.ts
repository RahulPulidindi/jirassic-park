import type { BrowserContext } from "playwright";

import { extractSkeletonInPage, signatures, type SkelNode } from "./normalizer.ts";
import type { ScreenTarget } from "./screens.ts";

export interface Capture {
  skeleton: SkelNode | null;
  signatures: string[];
  /** API-ish requests (xhr/fetch) the screen fired, as full URLs. */
  network: string[];
  fullPng: Buffer;
  focusPng: Buffer | null;
}

/** Drive one target to one screen state and capture all axes. */
export async function capture(ctx: BrowserContext, target: ScreenTarget, base: string): Promise<Capture> {
  const page = await ctx.newPage();
  const network: string[] = [];
  page.on("request", (req) => {
    const t = req.resourceType();
    if (t === "xhr" || t === "fetch") network.push(req.url());
  });

  await page.goto(target.url(base), { waitUntil: "domcontentloaded", timeout: 45000 });
  // Settle BEFORE interacting so the app has hydrated — in `next dev` the DOM is
  // present long before React wires up handlers, and a click that lands first is
  // silently dropped (the modal never opens). networkidle can hang on real
  // Jira's long-poll connections, so cap it and fall back to a fixed wait.
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(800);
  if (target.reach) await target.reach(page);
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(1200);

  // tsx/esbuild wraps named functions with a `__name(...)` helper that exists
  // in Node but not the browser. The function we pass to evaluate is stringified
  // and run in the page, so define a no-op `__name` in the same world first.
  await page.evaluate("window.__name = window.__name || function (f) { return f; };");
  const skeleton = (await page.evaluate(extractSkeletonInPage, target.focus)) as SkelNode | null;
  const fullPng = await page.screenshot({ fullPage: true });

  let focusPng: Buffer | null = null;
  const focusEl = page.locator(target.focus).first();
  if (await focusEl.count().then((n) => n > 0).catch(() => false)) {
    focusPng = await focusEl.screenshot().catch(() => null);
  }

  await page.close();
  return { skeleton, signatures: signatures(skeleton), network, fullPng, focusPng };
}
