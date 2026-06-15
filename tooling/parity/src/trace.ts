/**
 * Mechanical action-trace recorder. Drives a workflow step-by-step on one
 * target and, at each step, records the *observable consequences*:
 *   - which field/affordance signatures appeared or disappeared (DOM delta)
 *   - which XHR/fetch endpoints fired during the step (network delta)
 *
 * The trace is captured deterministically; comprehension (what the deltas
 * *mean*) is left to the detection LLM. A step that throws is recorded as
 * `ok: false` rather than aborting the run — a failed step is a real signal
 * (e.g. JP has no work-type picker to drive).
 */
import type { BrowserContext } from "playwright";

import { normalizeEndpoint } from "./differ.ts";
import { multisetDelta, settle, snapshotSignatures } from "./util.ts";
import type { WorkflowTarget } from "./workflows.ts";

export interface StepObservation {
  label: string;
  ok: boolean;
  error?: string;
  /** Field/affordance signatures that appeared after this step. */
  appeared: string[];
  /** ...and those that disappeared. */
  disappeared: string[];
  /** Normalized endpoints requested during this step. */
  requests: string[];
}

export interface WorkflowTrace {
  workflow: string;
  target: "jira" | "jp";
  /** Field set observed at the starting state, before any step. */
  initialFields: string[];
  steps: StepObservation[];
}

export async function trace(
  ctx: BrowserContext,
  workflow: WorkflowTarget,
  base: string,
  workflowName: string,
  targetName: "jira" | "jp",
): Promise<WorkflowTrace> {
  const page = await ctx.newPage();

  // Accumulate network as (index, url); steps slice it by marking the length.
  const net: string[] = [];
  page.on("request", (req) => {
    const t = req.resourceType();
    if (t === "xhr" || t === "fetch") net.push(req.url());
  });

  await page.goto(workflow.url(base), { waitUntil: "domcontentloaded", timeout: 45000 });
  await settle(page);

  let prevFields = await snapshotSignatures(page, workflow.observe);
  const initialFields = prevFields;

  const steps: StepObservation[] = [];
  for (const step of workflow.steps) {
    const netStart = net.length;
    let ok = true;
    let error: string | undefined;
    try {
      await step.run(page);
      await settle(page);
    } catch (e) {
      ok = false;
      error = (e as Error).message;
    }

    const fields = await snapshotSignatures(page, workflow.observe).catch(() => prevFields);
    const { appeared, disappeared } = multisetDelta(prevFields, fields);
    const requests = [...new Set(net.slice(netStart).map(normalizeEndpoint))].sort();

    steps.push({ label: step.label, ok, error, appeared, disappeared, requests });
    prevFields = fields;
  }

  await page.close();
  return { workflow: workflowName, target: targetName, initialFields, steps };
}
