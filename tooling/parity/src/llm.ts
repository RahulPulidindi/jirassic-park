/**
 * Thin Anthropic helpers shared by detect.ts and judge.ts.
 */
import Anthropic from "@anthropic-ai/sdk";

import { requireEnv } from "../config.ts";

let client: Anthropic | null = null;

export function anthropic(): Anthropic {
  if (!client) client = new Anthropic({ apiKey: requireEnv("ANTHROPIC_API_KEY") });
  return client;
}

/** A base64 PNG image content block. */
export function pngBlock(buf: Buffer): Anthropic.ImageBlockParam {
  return { type: "image", source: { type: "base64", media_type: "image/png", data: buf.toString("base64") } };
}

/** Concatenate all text blocks of a message response. */
export function textOf(msg: Anthropic.Message): string {
  return msg.content
    .filter((b): b is Anthropic.TextBlock => b.type === "text")
    .map((b) => b.text)
    .join("\n");
}

/** Parse the first JSON object out of a model response, tolerating prose/fences. */
export function parseJsonObject<T>(text: string): T {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  const candidate = fenced ? fenced[1] : text;
  const start = candidate.indexOf("{");
  const end = candidate.lastIndexOf("}");
  if (start === -1 || end === -1 || end < start) {
    throw new Error(`No JSON object found in model response:\n${text.slice(0, 500)}`);
  }
  return JSON.parse(candidate.slice(start, end + 1)) as T;
}
