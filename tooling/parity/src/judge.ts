/**
 * Judge: after a patch, decide whether a screen has reached acceptable parity.
 * Two signals, combined by the orchestrator:
 *   - semantic verdict (this file): Opus compares the post-patch JP screenshot
 *     against real Jira and the (now hopefully resolved) discrepancy list.
 *   - pixel guardrail (orchestrator, via visualDiff): the targeted screen's
 *     focus mismatch must not regress vs baseline.
 *
 * A screen passes only when the judge accepts AND the guardrail holds, so the
 * non-reproducible judge can never drive the env into a worse state unnoticed.
 */
import { config } from "../config.ts";
import type { Discrepancy } from "./detect.ts";
import { anthropic, parseJsonObject, pngBlock, textOf } from "./llm.ts";

export interface Verdict {
  screen: string;
  accept: boolean;
  score: number; // 0..1 subjective parity
  remaining: string[];
}

const SYSTEM = `You are judging whether a Jira clone screen (Jirassic Park) has reached acceptable visual + behavioral parity with real Jira. You get the real Jira screenshot (ground truth), the current Jirassic Park screenshot, and the discrepancies that were previously reported for this screen.

Accept only if a coding agent looking at both would consider the previously-reported material discrepancies resolved (minor pixel/shade noise is fine). Respond with ONLY:
{"accept":<bool>,"score":<0..1>,"remaining":["<unresolved discrepancy>"]}`;

export async function judge(
  screen: string,
  jiraPng: Buffer,
  jpPng: Buffer,
  priorDiscrepancies: Discrepancy[],
): Promise<Verdict> {
  const msg = await anthropic().messages.create({
    model: config.ranger.judgeModel,
    max_tokens: 1024,
    system: SYSTEM,
    messages: [
      {
        role: "user",
        content: [
          { type: "text", text: `Screen: ${screen}\nreal Jira (ground truth):` },
          pngBlock(jiraPng),
          { type: "text", text: "Jirassic Park (current):" },
          pngBlock(jpPng),
          {
            type: "text",
            text: `Previously reported discrepancies for this screen:\n${JSON.stringify(
              priorDiscrepancies,
              null,
              2,
            )}`,
          },
        ],
      },
    ],
  });

  const parsed = parseJsonObject<{ accept: boolean; score: number; remaining: string[] }>(textOf(msg));
  return {
    screen,
    accept: Boolean(parsed.accept),
    score: typeof parsed.score === "number" ? parsed.score : 0,
    remaining: parsed.remaining ?? [],
  };
}
