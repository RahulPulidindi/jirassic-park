/**
 * One-time interactive login to real Jira. Opens a headed browser; you log in
 * by hand (handles SSO / 2FA / Google), then press Enter here to save the
 * session. Subsequent `npm run run` invocations reuse it unattended.
 */
import { mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { createInterface } from "node:readline/promises";

import { chromium } from "playwright";

import { config } from "../config.ts";

async function main() {
  await mkdir(dirname(config.jira.authPath), { recursive: true });

  const browser = await chromium.launch({ headless: false });
  const ctx = await browser.newContext({ viewport: config.viewport });
  const page = await ctx.newPage();
  await page.goto(config.jira.baseUrl);

  console.log("\nA browser window opened. Log in to Jira fully (until you see your dashboard).");
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  await rl.question("When you're logged in, press Enter here to save the session\u2026 ");
  rl.close();

  await ctx.storageState({ path: config.jira.authPath });
  console.log(`Saved session to ${config.jira.authPath}`);
  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
