import pixelmatch from "pixelmatch";
import { PNG } from "pngjs";

export interface StructuralDiff {
  matched: number;
  /** Signatures present in real Jira but absent in Jirassic Park. */
  missing: string[];
  /** Signatures present in Jirassic Park but absent in real Jira. */
  extra: string[];
}

/** Multiset diff of two signature lists. */
export function structuralDiff(jira: string[], jp: string[]): StructuralDiff {
  const count = (xs: string[]) => {
    const m = new Map<string, number>();
    for (const x of xs) m.set(x, (m.get(x) ?? 0) + 1);
    return m;
  };
  const a = count(jira);
  const b = count(jp);
  const keys = new Set([...a.keys(), ...b.keys()]);
  const missing: string[] = [];
  const extra: string[] = [];
  let matched = 0;
  for (const k of keys) {
    const ca = a.get(k) ?? 0;
    const cb = b.get(k) ?? 0;
    matched += Math.min(ca, cb);
    if (ca > cb) for (let i = 0; i < ca - cb; i++) missing.push(k);
    if (cb > ca) for (let i = 0; i < cb - ca; i++) extra.push(k);
  }
  missing.sort();
  extra.sort();
  return { matched, missing, extra };
}

export interface NetworkDiff {
  shared: string[];
  jiraOnly: string[];
  jpOnly: string[];
}

/** Normalize a URL to an endpoint pattern: drop origin + query, mask ids. */
export function normalizeEndpoint(url: string): string {
  let path = url;
  try {
    path = new URL(url).pathname;
  } catch {
    /* keep as-is */
  }
  return path
    .replace(/\/\d+/g, "/{id}")
    .replace(/\/[0-9a-f]{8,}/gi, "/{id}")
    .replace(/\/[A-Z][A-Z0-9]+-\d+/g, "/{key}");
}

export function networkDiff(jira: string[], jp: string[]): NetworkDiff {
  const a = new Set(jira.map(normalizeEndpoint));
  const b = new Set(jp.map(normalizeEndpoint));
  const shared = [...a].filter((x) => b.has(x)).sort();
  const jiraOnly = [...a].filter((x) => !b.has(x)).sort();
  const jpOnly = [...b].filter((x) => !a.has(x)).sort();
  return { shared, jiraOnly, jpOnly };
}

export interface VisualDiff {
  mismatch: number; // 0..1 fraction of differing pixels over the compared area
  width: number;
  height: number;
  diffPng: Buffer;
}

/**
 * Compare two PNGs by cropping both to their common top-left region (so we
 * don't need an image-resize dependency). This is a rough layout *signal*,
 * intentionally weighted low — exact pixels are not the goal.
 */
export function visualDiff(aBuf: Buffer, bBuf: Buffer): VisualDiff {
  const a = PNG.sync.read(aBuf);
  const b = PNG.sync.read(bBuf);
  const width = Math.min(a.width, b.width);
  const height = Math.min(a.height, b.height);

  const crop = (src: PNG): Buffer => {
    const out = new PNG({ width, height });
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const si = (src.width * y + x) << 2;
        const di = (width * y + x) << 2;
        out.data[di] = src.data[si];
        out.data[di + 1] = src.data[si + 1];
        out.data[di + 2] = src.data[si + 2];
        out.data[di + 3] = src.data[si + 3];
      }
    }
    return out.data as Buffer;
  };

  const ad = crop(a);
  const bd = crop(b);
  const diff = new PNG({ width, height });
  const differing = pixelmatch(ad, bd, diff.data, width, height, { threshold: 0.1 });
  return {
    mismatch: differing / (width * height),
    width,
    height,
    diffPng: PNG.sync.write(diff),
  };
}
