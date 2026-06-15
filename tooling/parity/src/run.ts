/**
 * Orchestrator: for each screen, capture real Jira + Jirassic Park, normalize,
 * diff, and write a per-screen report plus a browsable index.html.
 *
 * Two auth sessions, not one per screen: real Jira via the saved storageState,
 * JP via a demo token injected into localStorage. Screens are navigations
 * within those sessions (a fresh page per screen for isolation).
 */
import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

import { chromium } from "playwright";

import { config } from "../config.ts";
import { capture } from "./recorder.ts";
import { networkDiff, structuralDiff, visualDiff } from "./differ.ts";
import { screens } from "./screens.ts";

interface ScreenReport {
  screen: string;
  structural: ReturnType<typeof structuralDiff>;
  network: ReturnType<typeof networkDiff>;
  visual: { full: number; focus: number | null };
}

async function main() {
  if (!existsSync(config.jira.authPath)) {
    console.error(`No saved Jira session at ${config.jira.authPath}. Run:  npm run login`);
    process.exit(1);
  }

  const browser = await chromium.launch({ headless: true });

  // Session 1: real Jira (oracle).
  const jiraCtx = await browser.newContext({
    storageState: config.jira.authPath,
    viewport: config.viewport,
  });

  // Session 2: Jirassic Park (subject) — inject the demo token before page JS.
  const jpCtx = await browser.newContext({ viewport: config.viewport });
  await jpCtx.addInitScript((token) => {
    try {
      window.localStorage.setItem("jp_api_token", token as string);
    } catch {
      /* ignore */
    }
  }, config.jp.token);

  const reports: ScreenReport[] = [];

  for (const screen of screens) {
    console.log(`\n=== ${screen.name} ===`);
    const dir = join(config.outDir, screen.name);
    await mkdir(dir, { recursive: true });

    let jira, jp;
    try {
      console.log("  capturing real Jira\u2026");
      jira = await capture(jiraCtx, screen.jira, config.jira.baseUrl);
      console.log("  capturing Jirassic Park\u2026");
      jp = await capture(jpCtx, screen.jp, config.jp.baseUrl);
    } catch (e) {
      console.error(`  capture failed: ${(e as Error).message}`);
      continue;
    }

    const structural = structuralDiff(jira.signatures, jp.signatures);
    const network = networkDiff(jira.network, jp.network);

    const fullV = visualDiff(jira.fullPng, jp.fullPng);
    let focusMismatch: number | null = null;
    if (jira.focusPng && jp.focusPng) {
      const fv = visualDiff(jira.focusPng, jp.focusPng);
      focusMismatch = fv.mismatch;
      await writeFile(join(dir, "focus.diff.png"), fv.diffPng);
    }

    await Promise.all([
      writeFile(join(dir, "jira.full.png"), jira.fullPng),
      writeFile(join(dir, "jp.full.png"), jp.fullPng),
      writeFile(join(dir, "full.diff.png"), fullV.diffPng),
      writeFile(join(dir, "jira.skeleton.json"), JSON.stringify(jira.skeleton, null, 2)),
      writeFile(join(dir, "jp.skeleton.json"), JSON.stringify(jp.skeleton, null, 2)),
      jira.focusPng ? writeFile(join(dir, "jira.focus.png"), jira.focusPng) : Promise.resolve(),
      jp.focusPng ? writeFile(join(dir, "jp.focus.png"), jp.focusPng) : Promise.resolve(),
    ]);

    const report: ScreenReport = {
      screen: screen.name,
      structural,
      network,
      visual: { full: fullV.mismatch, focus: focusMismatch },
    };
    await writeFile(join(dir, "report.json"), JSON.stringify(report, null, 2));
    reports.push(report);

    console.log(
      `  structural: ${structural.matched} matched, ${structural.missing.length} missing, ${structural.extra.length} extra`,
    );
    console.log(`  network: ${network.jiraOnly.length} jira-only endpoints`);
    console.log(`  visual: full ${(fullV.mismatch * 100).toFixed(1)}% differing`);
  }

  await writeFile(join(config.outDir, "index.html"), renderIndex(reports));
  console.log(`\nDone. Open ${join(config.outDir, "index.html")}`);
  await browser.close();
}

function esc(s: string): string {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]!);
}

function renderIndex(reports: ScreenReport[]): string {
  const sections = reports
    .map((r) => {
      const list = (xs: string[]) =>
        xs.length ? `<ul>${xs.map((x) => `<li><code>${esc(x)}</code></li>`).join("")}</ul>` : "<p>none</p>";
      return `
      <section>
        <h2>${esc(r.screen)}</h2>
        <p><b>Structural:</b> ${r.structural.matched} matched ·
           ${r.structural.missing.length} missing · ${r.structural.extra.length} extra</p>
        <p><b>Visual:</b> full ${(r.visual.full * 100).toFixed(1)}% differing${
          r.visual.focus != null ? ` · focus ${(r.visual.focus * 100).toFixed(1)}%` : ""
        }</p>
        <div class="imgs">
          <figure><figcaption>real Jira</figcaption><img src="${r.screen}/jira.full.png"></figure>
          <figure><figcaption>Jirassic Park</figcaption><img src="${r.screen}/jp.full.png"></figure>
          <figure><figcaption>diff</figcaption><img src="${r.screen}/full.diff.png"></figure>
        </div>
        <details><summary>Missing in Jirassic Park (present in real Jira)</summary>${list(r.structural.missing)}</details>
        <details><summary>Extra in Jirassic Park</summary>${list(r.structural.extra)}</details>
        <details><summary>Endpoints only real Jira called</summary>${list(r.network.jiraOnly)}</details>
      </section>`;
    })
    .join("\n");

  return `<!doctype html><meta charset="utf-8"><title>Jira parity report</title>
<style>
  body{font:14px/1.5 system-ui,sans-serif;margin:2rem;max-width:1100px}
  section{border-top:1px solid #ddd;padding:1.5rem 0}
  .imgs{display:flex;gap:1rem;flex-wrap:wrap}
  .imgs img{width:320px;border:1px solid #ccc}
  figcaption{font-size:12px;color:#666}
  code{background:#f4f4f4;padding:1px 4px;border-radius:3px}
  details{margin:.4rem 0}
  summary{cursor:pointer;font-weight:600}
</style>
<h1>Jira \u2194 Jirassic Park parity</h1>
${sections}`;
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
