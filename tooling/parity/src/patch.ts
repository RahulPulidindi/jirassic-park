/**
 * Patch: drive a Cursor coding agent (via @cursor/sdk, local runtime) to fix
 * the reported discrepancies in the Jirassic Park source. Runs against the repo
 * root working tree; the orchestrator has already put us on a dedicated branch,
 * so edits land there for human review — never an auto-merge.
 */
import { setMaxListeners } from "node:events";

import { Agent, CursorAgentError } from "@cursor/sdk";

import { config, repoRoot, requireEnv } from "../config.ts";
import type { Discrepancy } from "./detect.ts";

export interface PatchResult {
  status: "finished" | "error" | "cancelled";
  runId: string;
  summary: string;
}

function buildPrompt(discrepancies: Discrepancy[]): string {
  const lines = discrepancies
    .map(
      (d, i) =>
        `${i + 1}. [${d.screen} · ${d.axis} · ${d.severity}] ${d.summary}\n` +
        `   evidence: ${d.evidence}\n` +
        `   suspected files: ${d.suspected_files.join(", ") || "(discover)"}\n` +
        `   suggested fix: ${d.suggested_fix}`,
    )
    .join("\n\n");

  return `You are improving "Jirassic Park" (JP), a Jira clone, so it matches real Atlassian Jira more faithfully. A differential parity oracle compared our UI/behavior against real Jira and found the discrepancies below. Real Jira is the ground truth.

## How JP runs (important — do not get this wrong)
The system under test is the **Next.js frontend** in \`frontend/\`, served by a hot-reloading \`next dev\` server on http://localhost:3000. It talks to a backend API on http://localhost:8080. The parity loop re-captures :3000 after you edit, so **only edits under \`frontend/\` are observed**. You are NOT debugging how the app is served — it is already served correctly. If a page renders, the React app is mounted; do not "fix" static-file serving.

Screen → primary file(s):
- create-issue → frontend/components/CreateIssueModal.tsx, frontend/components/Dropdown.tsx, frontend/lib/jira-testids.ts
- issue-detail → frontend/app/issue/page.tsx and the components it renders

## Hard constraints (a violation makes the patch worse, not better)
1. **Edit ONLY existing files under \`frontend/\`.** Do NOT touch backend/, Docker, Makefile, next.config.*, CI, package.json, or anything about how the app is built or served.
2. **Do NOT create new routes, pages, or files.** If an entire screen/page appears to be missing, that is OUT OF SCOPE — skip it and say so. Never scaffold a new page/dashboard/API to close a gap.
3. **Do NOT add a hidden/empty element just to satisfy a selector.** Fix the real component. For behavioral gaps (e.g. fields that should appear when work type changes), implement the actual behavior in the existing component.
4. Keep edits minimal and localized to the named components. Do not refactor unrelated code; do not touch tests.
5. Preserve existing data-testid / ARIA conventions (see frontend/lib/jira-testids.ts).
6. If you cannot fix an item within these constraints, leave it unchanged and note why. Doing nothing is better than a broad change that regresses other screens.

Discrepancies:
${lines}

When done, briefly summarize the files you changed and why (and list any items you intentionally skipped).`;
}

export async function patch(discrepancies: Discrepancy[]): Promise<PatchResult> {
  // The SDK attaches many abort listeners to a shared signal while streaming;
  // raise the cap so Node doesn't print a spurious MaxListeners warning.
  setMaxListeners(64);
  const apiKey = requireEnv("CURSOR_API_KEY");
  const prompt = buildPrompt(discrepancies);

  const agent = await Agent.create({
    apiKey,
    model: { id: config.ranger.patchModel },
    name: "ranger-patcher",
    // Explicit local runtime (avoids the silent-local trap); inline config only.
    local: { cwd: repoRoot, settingSources: [] },
  });

  try {
    const run = await agent.send(prompt);
    console.log(`    patch run ${run.id} (agent ${agent.agentId})`);

    for await (const event of run.stream()) {
      if (event.type === "assistant") {
        for (const block of event.message.content) {
          if (block.type === "text") process.stdout.write(block.text);
        }
      }
    }
    const result = await run.wait();
    process.stdout.write("\n");
    return { status: result.status, runId: result.id, summary: result.result ?? "" };
  } catch (err) {
    if (err instanceof CursorAgentError) {
      // Never started (auth/config/network) — distinct from a run that failed.
      console.error(`    patch agent failed to start: ${err.message} (retryable=${err.isRetryable})`);
      return { status: "error", runId: "", summary: err.message };
    }
    throw err;
  } finally {
    await agent[Symbol.asyncDispose]();
  }
}
