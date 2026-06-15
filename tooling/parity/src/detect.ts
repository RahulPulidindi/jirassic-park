/**
 * Detection: hand a multimodal Opus model the (real Jira, Jirassic Park) pair
 * of screenshots per screen plus the mechanical action traces, and ask it for
 * a *structured* discrepancy list. This is the semantic layer — it understands
 * "JP doesn't re-render fields when work type changes" in a way pixel/DOM diffs
 * can't. Output is deliberately structured so the patch agent can act on it.
 *
 * This step is non-reproducible by nature; that's acceptable because it's a
 * dev-time signal gated downstream by a deterministic pixel guardrail, not a
 * training reward.
 */
import Anthropic from "@anthropic-ai/sdk";

import { config } from "../config.ts";
import { anthropic, parseJsonObject, pngBlock, textOf } from "./llm.ts";
import type { WorkflowTrace } from "./trace.ts";

export interface Discrepancy {
  screen: string;
  axis: "visual" | "behavioral";
  severity: "high" | "medium" | "low";
  summary: string;
  evidence: string;
  suspected_files: string[];
  suggested_fix: string;
}

export interface ScreenShots {
  name: string;
  jiraPng: Buffer;
  jpPng: Buffer;
}

export interface TracePair {
  jira: WorkflowTrace;
  jp: WorkflowTrace;
}

const REPO_MAP = `Jirassic Park is the system under test. It is a Next.js app under frontend/, served by next dev on :3000. Fixes are made by editing EXISTING frontend/ files only:
- Visual / component structure: frontend/components/*.tsx (CreateIssueModal.tsx, AppShell.tsx, Dropdown.tsx), frontend/app/**/page.tsx
- Field/affordance testids: frontend/lib/jira-testids.ts
- Behavioral (which fields exist, what changes on work-type change): frontend/components/CreateIssueModal.tsx

Scope rules for what you report:
- Only report discrepancies fixable by editing an EXISTING frontend component. suspected_files must be existing frontend/ paths.
- Do NOT report "whole page/screen is missing" gaps and do NOT suggest creating new routes, pages, or backend endpoints — those are out of scope for the patcher and will be ignored.
- Compare like states only: if the two screenshots are clearly different *pages* (not the same page with differences), that is a fixture/config issue, not a discrepancy to patch — skip it.`;

const SYSTEM = `You are a senior front-end + fidelity engineer comparing a clone (Jirassic Park, "JP") against real Atlassian Jira. Real Jira is the ground truth. You receive, per screen, two screenshots (real Jira then JP) and, where available, two mechanical action traces (real Jira then JP) listing per-step field-set deltas and network calls.

Report only discrepancies that an agent training in JP would actually notice: visual layout/affordance differences and behavioral differences (fields that appear/disappear on interaction, workflow steps that fail in one system, API calls that one fires and the other doesn't). Ignore: cosmetic color/font shade noise, telemetry/personalization/ads endpoints unique to real Jira, and absolute text content of seeded data.

Respond with ONLY a JSON object of the form:
{"discrepancies":[{"screen":"<name>","axis":"visual|behavioral","severity":"high|medium|low","summary":"<one line>","evidence":"<what in the screenshots/traces shows it>","suspected_files":["<repo path>"],"suggested_fix":"<concrete change>"}]}
If there are no material discrepancies, return {"discrepancies":[]}.`;

export async function detect(screens: ScreenShots[], traces: TracePair[]): Promise<Discrepancy[]> {
  const content: Anthropic.ContentBlockParam[] = [
    { type: "text", text: `${REPO_MAP}\n\nCompare the following screens and traces.` },
  ];

  for (const s of screens) {
    content.push({ type: "text", text: `\n=== SCREEN: ${s.name} — real Jira (ground truth):` });
    content.push(pngBlock(s.jiraPng));
    content.push({ type: "text", text: `=== SCREEN: ${s.name} — Jirassic Park (under test):` });
    content.push(pngBlock(s.jpPng));
  }

  for (const t of traces) {
    content.push({
      type: "text",
      text: `\n=== WORKFLOW TRACE: ${t.jira.workflow}\nreal Jira:\n${JSON.stringify(
        t.jira,
        null,
        2,
      )}\nJirassic Park:\n${JSON.stringify(t.jp, null, 2)}`,
    });
  }

  const msg = await anthropic().messages.create({
    model: config.ranger.detectModel,
    max_tokens: 4096,
    system: SYSTEM,
    messages: [{ role: "user", content }],
  });

  const parsed = parseJsonObject<{ discrepancies: Discrepancy[] }>(textOf(msg));
  return parsed.discrepancies ?? [];
}
