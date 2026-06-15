/**
 * Ranger — the autonomous parity loop.
 *
 *   capture (Playwright)  ->  detect (Opus, multimodal)  ->  patch (Cursor SDK)
 *      ^                                                          |
 *      +------------------  judge + pixel guardrail  <------------+
 *
 * Real Jira is captured ONCE into committed golden fixtures (the frozen
 * target); the loop only re-captures Jirassic Park, so the only thing changing
 * between iterations is our own code. A screen passes when the Opus judge
 * accepts AND the deterministic focus-region pixel mismatch hasn't regressed
 * past baseline. Patches land on a dedicated branch for human review.
 *
 * Usage:
 *   npm run ranger:fixtures              # one-time: capture real Jira goldens (needs `npm run login`)
 *   npm run ranger                       # full loop over all screens + workflows
 *   npm run ranger -- --screen create-issue --max-iters 4
 *   npm run ranger -- --detect-only      # capture + detect + report, no patching
 *   npm run ranger -- --no-branch        # don't create a git branch
 */
import { execFileSync, execSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

import { chromium, type Browser, type BrowserContext } from "playwright";

import { config, repoRoot } from "../config.ts";
import { detect, type Discrepancy, type ScreenShots, type TracePair } from "./detect.ts";
import { visualDiff } from "./differ.ts";
import { judge, type Verdict } from "./judge.ts";
import { openPullRequest, type PrScreen } from "./pr.ts";
import { patch } from "./patch.ts";
import { capture } from "./recorder.ts";
import { screens } from "./screens.ts";
import { trace, type WorkflowTrace } from "./trace.ts";
import { workflows } from "./workflows.ts";

interface Args {
  captureFixtures: boolean;
  detectOnly: boolean;
  noBranch: boolean;
  only?: string;
  /** Run every defined screen (default loop is the reliable subset). */
  allScreens: boolean;
  maxIters: number;
  /** JP base URL the loop captures against (default = config; --jp-dev = :3000). */
  jpBase: string;
  /** Open a GitHub PR (with before/after screenshots) once patches are made. */
  pr: boolean;
}

/**
 * The default loop targets screens where JP has a genuine, comparable
 * counterpart. `for-you` is excluded by default: JP has no for-you page, so the
 * comparison is apples-to-oranges and tempts the patcher into scaffolding an
 * entire new screen. Opt in with `--screen for-you` or `--all-screens`.
 */
const DEFAULT_SCREENS = ["create-issue", "issue-detail"];

function parseArgs(argv: string[]): Args {
  const a: Args = {
    captureFixtures: argv.includes("--capture-fixtures"),
    detectOnly: argv.includes("--detect-only"),
    noBranch: argv.includes("--no-branch"),
    allScreens: argv.includes("--all-screens"),
    maxIters: config.ranger.maxIters,
    jpBase: config.jp.baseUrl,
    pr: argv.includes("--pr"),
  };
  const screenIdx = argv.indexOf("--screen");
  if (screenIdx !== -1 && argv[screenIdx + 1]) a.only = argv[screenIdx + 1];
  const itersIdx = argv.indexOf("--max-iters");
  if (itersIdx !== -1 && argv[itersIdx + 1]) a.maxIters = Number(argv[itersIdx + 1]);
  // --jp-dev targets the hot-reloading `next dev` server so the loop sees patches.
  if (argv.includes("--jp-dev")) a.jpBase = "http://localhost:3000";
  const jpUrlIdx = argv.indexOf("--jp-url");
  if (jpUrlIdx !== -1 && argv[jpUrlIdx + 1]) a.jpBase = argv[jpUrlIdx + 1];
  return a;
}

/**
 * Block until the JP server answers (any non-5xx), so a recapture never races
 * a `next dev` recompile or a `uvicorn --reload` restart triggered by a patch.
 */
async function waitForServer(url: string, timeoutMs = 90000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(url, { method: "GET" });
      if (r.status < 500) return;
    } catch {
      /* not up yet */
    }
    await new Promise((res) => setTimeout(res, 1000));
  }
  console.warn(`  JP did not become ready at ${url} within ${timeoutMs}ms; capturing anyway.`);
}

const screenDir = (name: string) => join(config.fixturesDir, "screens", name);
const workflowDir = (name: string) => join(config.fixturesDir, "workflows", name);

const sleep = (ms: number) => new Promise((res) => setTimeout(res, ms));

/** Run a git command in the repo root, returning trimmed stdout. */
function git(args: string[]): string {
  return execFileSync("git", args, { cwd: repoRoot, encoding: "utf8" }).trim();
}

/** Commit whatever the patch changed as a checkpoint. Returns true if it committed. */
function commitCheckpoint(message: string): boolean {
  // Stage only the app dirs the patch is allowed to touch, so we never sweep up
  // unrelated untracked files (root .gitignore, tooling/out, etc.).
  git(["add", "-A", "frontend", "backend"]);
  try {
    git(["commit", "-m", message]);
    return true;
  } catch {
    return false; // nothing staged (patch made no tracked change)
  }
}

/** Discard the uncommitted patch (tracked edits + any new frontend/backend files). */
function revertWorkingTree(): void {
  git(["reset", "--hard", "HEAD"]);
  // Remove untracked files the patch may have created, but only in app dirs so
  // we never touch tooling/out, fixtures, node_modules, or ignored caches.
  try {
    git(["clean", "-fd", "frontend", "backend"]);
  } catch {
    /* nothing to clean */
  }
}

/** Mean focus mismatch over the screens present in `names` and the map. */
function meanOver(map: Map<string, number>, names: string[]): number | null {
  const vals = names.map((n) => map.get(n)).filter((v): v is number => typeof v === "number");
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
}

async function newJpContext(browser: Browser): Promise<BrowserContext> {
  const ctx = await browser.newContext({ viewport: config.viewport });
  await ctx.addInitScript((token) => {
    try {
      window.localStorage.setItem("jp_api_token", token as string);
    } catch {
      /* ignore */
    }
  }, config.jp.token);
  return ctx;
}

/**
 * Capture a JP screen, retrying transient failures (a cold `next dev` route
 * compile, a post-patch recompile, or an HMR full-reload can make the first
 * interaction race). Between attempts we re-confirm the server is up and back
 * off, so a flaky reach doesn't drop a screen from the comparison.
 */
async function captureWithRetry(
  ctx: BrowserContext,
  target: Parameters<typeof capture>[1],
  base: string,
  attempts = 3,
): Promise<ReturnType<typeof capture>> {
  let lastErr: unknown;
  for (let i = 0; i < attempts; i++) {
    try {
      return await capture(ctx, target, base);
    } catch (e) {
      lastErr = e;
      await waitForServer(base);
      await sleep(1500 * (i + 1));
    }
  }
  throw lastErr;
}

/** Pre-load each route once so `next dev` compiles it before we measure. */
async function warmUp(ctx: BrowserContext, urls: string[]): Promise<void> {
  const unique = [...new Set(urls)];
  for (const u of unique) {
    const p = await ctx.newPage();
    try {
      await p.goto(u, { waitUntil: "domcontentloaded", timeout: 45000 });
      await p.waitForTimeout(1500);
    } catch {
      /* a warm-up miss is fine; the measured capture has retries */
    }
    await p.close();
  }
}

/** One-time: capture real Jira goldens (screenshots + traces) into fixtures/. */
async function captureFixtures(only?: string): Promise<void> {
  if (!existsSync(config.jira.authPath)) {
    console.error(`No saved Jira session at ${config.jira.authPath}. Run:  npm run login`);
    process.exit(1);
  }
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ storageState: config.jira.authPath, viewport: config.viewport });

  for (const screen of screens.filter((s) => !only || s.name === only)) {
    console.log(`fixture screen: ${screen.name}`);
    const dir = screenDir(screen.name);
    await mkdir(dir, { recursive: true });
    const cap = await capture(ctx, screen.jira, config.jira.baseUrl);
    await writeFile(join(dir, "jira.full.png"), cap.fullPng);
    if (cap.focusPng) await writeFile(join(dir, "jira.focus.png"), cap.focusPng);
  }

  for (const wf of workflows.filter((w) => !only || w.name === only)) {
    console.log(`fixture workflow: ${wf.name}`);
    const dir = workflowDir(wf.name);
    await mkdir(dir, { recursive: true });
    const t = await trace(ctx, wf.jira, config.jira.baseUrl, wf.name, "jira");
    await writeFile(join(dir, "jira.trace.json"), JSON.stringify(t, null, 2));
  }

  await browser.close();
  console.log(`\nGoldens written under ${config.fixturesDir}/. Commit them; the loop diffs against these.`);
}

interface JiraFixtures {
  screens: Map<string, { full: Buffer; focus: Buffer | null }>;
  traces: Map<string, WorkflowTrace>;
}

async function loadJiraFixtures(only?: string): Promise<JiraFixtures> {
  const fx: JiraFixtures = { screens: new Map(), traces: new Map() };
  for (const screen of screens.filter((s) => !only || s.name === only)) {
    const full = join(screenDir(screen.name), "jira.full.png");
    if (!existsSync(full)) {
      console.error(`Missing golden for "${screen.name}". Run:  npm run ranger:fixtures`);
      process.exit(1);
    }
    const focus = join(screenDir(screen.name), "jira.focus.png");
    fx.screens.set(screen.name, {
      full: await readFile(full),
      focus: existsSync(focus) ? await readFile(focus) : null,
    });
  }
  for (const wf of workflows.filter((w) => !only || w.name === only)) {
    const p = join(workflowDir(wf.name), "jira.trace.json");
    if (existsSync(p)) fx.traces.set(wf.name, JSON.parse(await readFile(p, "utf8")) as WorkflowTrace);
  }
  return fx;
}

function createBranch(): string | null {
  try {
    const name = `ranger/${new Date().toISOString().replace(/[:.]/g, "-")}`;
    execSync(`git checkout -b ${name}`, { cwd: repoRoot, stdio: "pipe" });
    console.log(`On branch ${name} (patches land here for review).`);
    return name;
  } catch (e) {
    console.warn(`Could not create a git branch (${(e as Error).message.split("\n")[0]}). Continuing on current branch.`);
    return null;
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));

  if (args.captureFixtures) {
    await captureFixtures(args.only);
    return;
  }

  const inScope = (name: string) =>
    args.only ? name === args.only : args.allScreens || DEFAULT_SCREENS.includes(name);
  const fx = await loadJiraFixtures(args.only);
  const activeScreens = screens.filter((s) => inScope(s.name));
  const activeWorkflows = workflows.filter((w) => inScope(w.name));

  console.log(`Capturing Jirassic Park at ${args.jpBase}`);
  if (!args.detectOnly && /:8080(\/|$)/.test(args.jpBase)) {
    console.warn(
      "  WARNING: :8080 serves the static export (baked into the container). Patches won't show up here.\n" +
        "  For the loop to converge, serve JP with hot-reload and pass --jp-dev:\n" +
        "    make dev-backend   # uvicorn :8080\n" +
        "    cd frontend && NEXT_PUBLIC_API_BASE=http://localhost:8080 npm run dev   # next dev :3000\n" +
        "    npm run ranger -- --jp-dev",
    );
  }

  const branch = args.detectOnly || args.noBranch ? null : createBranch();

  const runId = new Date().toISOString().replace(/[:.]/g, "-");
  const runDir = join(config.outDir, `run-${runId}`);
  await mkdir(runDir, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  await waitForServer(args.jpBase);

  // Warm next dev's route compiler so the first measured capture isn't racing a
  // cold compile (a common cause of a flaky "reach").
  const warmCtx = await newJpContext(browser);
  await warmUp(
    warmCtx,
    activeScreens.map((s) => s.jp.url(args.jpBase)),
  );
  await warmCtx.close();

  const baseline = new Map<string, number>(); // screen -> focus mismatch at iter 0 (judge guardrail)
  const firstJp = new Map<string, Buffer>(); // screen -> JP screenshot at iter 0 (PR "before")
  let success = false;
  let keptAnyPatch = false; // at least one patch committed as a checkpoint
  let stoppedByRegression = false;
  let lastDiscrepancies: Discrepancy[] = [];
  const iterationLog: unknown[] = [];

  // Hill-climb with rollback. `keptMismatch` is the parity of the last KEPT
  // state (a committed checkpoint). A patch is applied to the working tree; the
  // NEXT iteration re-captures and either commits it (parity held/improved) or
  // `git reset`s it (parity regressed) and stops. The loop therefore can never
  // end worse than it started, and bad patches never stack on each other.
  let keptMismatch: Map<string, number> | null = null;
  let patchPending = false; // an unvalidated patch sits in the working tree

  for (let iter = 0; iter < args.maxIters; iter++) {
    console.log(`\n========== iteration ${iter} ==========`);
    const iterDir = join(runDir, `iter-${iter}`);
    await mkdir(iterDir, { recursive: true });

    // Capture Jirassic Park (fresh each iteration to reflect patches).
    const jpCtx = await newJpContext(browser);
    const shots: ScreenShots[] = [];
    const focusMismatch = new Map<string, number>();

    for (const screen of activeScreens) {
      const jiraFx = fx.screens.get(screen.name)!;
      let jp;
      try {
        jp = await captureWithRetry(jpCtx, screen.jp, args.jpBase);
      } catch (e) {
        console.error(`  JP capture failed for ${screen.name}: ${(e as Error).message}`);
        continue;
      }
      await writeFile(join(iterDir, `${screen.name}.jp.full.png`), jp.fullPng);
      shots.push({ name: screen.name, jiraPng: jiraFx.full, jpPng: jp.fullPng });
      if (iter === 0) firstJp.set(screen.name, jp.fullPng);

      // Deterministic guardrail on the focused component.
      if (jiraFx.focus && jp.focusPng) {
        const fv = visualDiff(jiraFx.focus, jp.focusPng);
        focusMismatch.set(screen.name, fv.mismatch);
      } else {
        focusMismatch.set(screen.name, visualDiff(jiraFx.full, jp.fullPng).mismatch);
      }
      if (iter === 0) baseline.set(screen.name, focusMismatch.get(screen.name)!);
    }

    // Capture JP workflow traces and pair with the Jira goldens.
    const tracePairs: TracePair[] = [];
    for (const wf of activeWorkflows) {
      const jiraTrace = fx.traces.get(wf.name);
      if (!jiraTrace) continue;
      try {
        const jpTrace = await trace(jpCtx, wf.jp, args.jpBase, wf.name, "jp");
        tracePairs.push({ jira: jiraTrace, jp: jpTrace });
        await writeFile(join(iterDir, `${wf.name}.jp.trace.json`), JSON.stringify(jpTrace, null, 2));
      } catch (e) {
        console.error(`  JP trace failed for ${wf.name}: ${(e as Error).message}`);
      }
    }
    await jpCtx.close();

    for (const [name, m] of focusMismatch) {
      const base = baseline.get(name) ?? m;
      const tag = m > base + config.ranger.regressionEpsilon ? "  <-- above baseline" : "";
      console.log(`  focus mismatch ${name}: ${(m * 100).toFixed(1)}% (baseline ${(base * 100).toFixed(1)}%)${tag}`);
    }

    // ---- Hill-climb gate: validate the patch applied last iteration ----
    if (patchPending) {
      const common = activeScreens
        .map((s) => s.name)
        .filter((n) => focusMismatch.has(n) && keptMismatch!.has(n));
      const before = meanOver(keptMismatch!, common);
      const after = meanOver(focusMismatch, common);
      const regressed = before != null && after != null && after > before + config.ranger.regressionEpsilon;
      if (regressed) {
        console.log(
          `  patch REGRESSED parity ${(before! * 100).toFixed(1)}% -> ${(after! * 100).toFixed(1)}% ` +
            `over [${common.join(", ")}]; reverting it and stopping.`,
        );
        revertWorkingTree();
        stoppedByRegression = true;
        patchPending = false;
        iterationLog.push({ iter, focusMismatch: Object.fromEntries(focusMismatch), reverted: true });
        break;
      }
      const parityNote = before != null && after != null
        ? `${(before * 100).toFixed(1)}% -> ${(after * 100).toFixed(1)}%`
        : "unmeasured";
      if (commitCheckpoint(`Ranger: keep patch from iter ${iter - 1} (parity ${parityNote})`)) {
        keptAnyPatch = true;
        console.log(`  patch kept (parity ${parityNote}).`);
      } else {
        console.log("  patch produced no tracked change; continuing.");
      }
      keptMismatch = focusMismatch;
      patchPending = false;
    } else if (iter === 0) {
      keptMismatch = focusMismatch;
    }

    // Detect.
    console.log("  detecting discrepancies (Opus)\u2026");
    const discrepancies = await detect(shots, tracePairs);
    lastDiscrepancies = discrepancies;
    await writeFile(join(iterDir, "discrepancies.json"), JSON.stringify(discrepancies, null, 2));
    console.log(`  ${discrepancies.length} discrepancies found`);

    if (args.detectOnly) {
      iterationLog.push({ iter, focusMismatch: Object.fromEntries(focusMismatch), discrepancies });
      break;
    }

    if (discrepancies.length === 0) {
      console.log("  no discrepancies — parity reached.");
      success = true;
      iterationLog.push({ iter, focusMismatch: Object.fromEntries(focusMismatch), discrepancies: [] });
      break;
    }

    // Judge each screen (semantic) and combine with the pixel guardrail.
    const verdicts: Verdict[] = [];
    let allPass = true;
    for (const s of shots) {
      const prior = discrepancies.filter((d) => d.screen === s.name);
      const v = await judge(s.name, s.jiraPng, s.jpPng, prior);
      const base = baseline.get(s.name) ?? 0;
      const regressed = (focusMismatch.get(s.name) ?? 0) > base + config.ranger.regressionEpsilon;
      const pass = v.accept && !regressed;
      verdicts.push(v);
      console.log(`  judge ${s.name}: accept=${v.accept} score=${v.score.toFixed(2)} regressed=${regressed} -> ${pass ? "PASS" : "fail"}`);
      if (!pass) allPass = false;
    }
    await writeFile(join(iterDir, "verdicts.json"), JSON.stringify(verdicts, null, 2));

    iterationLog.push({ iter, focusMismatch: Object.fromEntries(focusMismatch), discrepancies, verdicts });

    if (allPass) {
      console.log("  all screens pass — parity reached.");
      success = true;
      break;
    }

    // Only patch if a FOLLOWING iteration can validate it — otherwise we'd exit
    // on an unvalidated (possibly regressing) change.
    if (iter >= args.maxIters - 1) {
      console.log("  reached max iterations; not applying an unvalidated patch.");
      break;
    }

    // Patch the working tree; the next iteration recaptures and keeps/reverts it.
    console.log("  patching (Cursor SDK)\u2026");
    const result = await patch(discrepancies);
    console.log(`  patch ${result.status} (run ${result.runId})`);
    if (result.status !== "finished") {
      console.error("  patch did not finish; discarding partial edits and stopping.");
      revertWorkingTree();
      break;
    }
    patchPending = true;

    // Let the patch land (next-dev recompile), then settle, so the next capture
    // sees the new UI.
    console.log("  waiting for JP to rebuild\u2026");
    await waitForServer(args.jpBase);
    await sleep(config.ranger.recompileSettleMs);
  }

  // Open a PR (with a fresh post-patch "after" screenshot) if we kept any patch.
  if (args.pr && keptAnyPatch) {
    if (!branch) {
      console.warn("\n--pr needs a branch, but none was created (--no-branch/--detect-only). Skipping PR.");
    } else {
      console.log("\nCapturing post-patch UI for the PR\u2026");
      await waitForServer(args.jpBase);
      const finalCtx = await newJpContext(browser);
      const prScreens: PrScreen[] = [];
      for (const screen of activeScreens) {
        let after: Buffer | null = null;
        try {
          after = (await captureWithRetry(finalCtx, screen.jp, args.jpBase)).fullPng;
        } catch (e) {
          console.error(`  post-patch capture failed for ${screen.name}: ${(e as Error).message}`);
        }
        prScreens.push({
          name: screen.name,
          before: firstJp.get(screen.name) ?? null,
          after,
          target: fx.screens.get(screen.name)?.full ?? null,
        });
      }
      await finalCtx.close();
      await openPullRequest({ branch, runId, screens: prScreens, discrepancies: lastDiscrepancies, success });
    }
  }

  await browser.close();

  const report = {
    branch,
    success,
    keptAnyPatch,
    stoppedByRegression,
    iterations: iterationLog,
    jpBase: args.jpBase,
    note: "Run the loop against the hot-reloading dev server (`--jp-dev`, i.e. next dev on :3000); patches to the static :8080 export won't show up between iterations.",
  };
  await writeFile(join(runDir, "report.json"), JSON.stringify(report, null, 2));
  const outcome = success
    ? "Parity reached."
    : stoppedByRegression
      ? "Stopped after reverting a regressing patch."
      : "Stopped without full parity.";
  console.log(`\n${outcome} Report: ${join(runDir, "report.json")}`);
  if (branch) console.log(`Review patches on branch ${branch}.`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
