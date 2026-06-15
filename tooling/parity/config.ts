/**
 * Targets the oracle compares. Everything is overridable via env so nothing
 * about your tenant is hard-baked into source.
 */
import { config as loadDotenv } from "dotenv";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

/** Repo root (two levels up from tooling/parity). Patch agent runs against it. */
export const repoRoot = resolve(here, "..", "..");

// Secrets (CURSOR_API_KEY, ANTHROPIC_API_KEY) live in the repo-root .env, which
// is gitignored. Loaded here so every module that imports config sees them.
loadDotenv({ path: resolve(repoRoot, ".env") });

export const config = {
  /** Real Jira — the oracle. Authenticated via a saved storageState (see login.ts). */
  jira: {
    baseUrl: process.env.JIRA_BASE_URL ?? "https://your-tenant.atlassian.net",
    authPath: ".auth/jira.storageState.json",
    /** An issue key that exists in your tenant, for the issue-detail screen. */
    issueKey: process.env.JIRA_ISSUE_KEY ?? "SCRUM-1",
    /** Path to a software board in your tenant, for the board screen. */
    boardPath: process.env.JIRA_BOARD_PATH ?? "/jira/software/projects/SCRUM/boards/1",
  },

  /** Jirassic Park — the subject. Auth is a demo bearer token in localStorage. */
  jp: {
    baseUrl: process.env.JP_BASE_URL ?? "http://localhost:8080",
    token: process.env.JP_TOKEN ?? "token_sarah_kim",
    /** An issue key that exists in the seed, for the issue-detail screen. */
    issueKey: process.env.JP_ISSUE_KEY ?? "SCRUM-1",
    /** A project key with a seeded board, for the board screen. */
    boardKey: process.env.JP_BOARD_KEY ?? "SCRUM",
  },

  /** A fixed viewport keeps screenshots comparable run-to-run. */
  viewport: { width: 1280, height: 900 },

  outDir: "out",

  /** Committed golden captures of real Jira (the frozen target). */
  fixturesDir: "fixtures",

  /**
   * Ranger: the autonomous detect -> patch -> judge loop.
   *
   * Detect/judge run on Anthropic (multimodal Opus); the patcher runs on a
   * Cursor model via @cursor/sdk. Model ids are env-overridable because the
   * lists evolve — if a default 404s, set RANGER_*_MODEL in .env.
   */
  ranger: {
    detectModel: process.env.RANGER_DETECT_MODEL ?? "claude-opus-4-6",
    judgeModel: process.env.RANGER_JUDGE_MODEL ?? "claude-opus-4-6",
    patchModel: process.env.RANGER_PATCH_MODEL ?? "composer-2.5",
    maxIters: Number(process.env.RANGER_MAX_ITERS ?? "4"),
    /**
     * A patch is only accepted if the targeted screen's focus-region pixel
     * mismatch didn't grow by more than this (no silent regression). Cheap,
     * reproducible guardrail that keeps the non-reproducible LLM judge honest.
     */
    regressionEpsilon: 0.01,
    /** Extra settle after JP is reachable again post-patch, for HMR to flush. */
    recompileSettleMs: Number(process.env.RANGER_RECOMPILE_SETTLE_MS ?? "2000"),
  },
} as const;

/** Fail fast with a clear message when a required secret is missing. */
export function requireEnv(name: string): string {
  const v = process.env[name];
  if (!v || !v.trim()) {
    console.error(
      `Missing required env var ${name}. Add it to ${resolve(repoRoot, ".env")} (one KEY=value per line).`,
    );
    process.exit(1);
  }
  return v.trim();
}
