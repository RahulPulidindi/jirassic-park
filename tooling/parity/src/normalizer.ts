/**
 * A normalized DOM node. We keep only *semantic* facts — role, testid, label,
 * field type, short text — and deliberately drop classes, inline styles,
 * generated ids, and telemetry attributes. That's both the clean-room boundary
 * (we capture structure, not markup) and what makes two different
 * implementations comparable.
 */
export interface SkelNode {
  tag: string;
  role?: string;
  testid?: string;
  label?: string;
  type?: string;
  text?: string;
  children: SkelNode[];
}

/**
 * Source of the function executed *inside the page* by Playwright. It must be
 * self-contained (no closure over module scope). Returns the skeleton root.
 */
export function extractSkeletonInPage(focusSelector: string): SkelNode | null {
  const MAX_NODES = 4000;
  let budget = MAX_NODES;

  const IGNORE_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "SVG", "PATH", "TEMPLATE", "LINK", "META"]);
  // testid attribute may be data-testid (Jira + JP) or data-test-id.
  const TESTID_ATTRS = ["data-testid", "data-test-id"];

  function visible(el: Element): boolean {
    const r = (el as HTMLElement).getBoundingClientRect?.();
    if (!r) return true;
    if (r.width === 0 && r.height === 0) return false;
    const s = window.getComputedStyle(el as HTMLElement);
    return s.display !== "none" && s.visibility !== "hidden";
  }

  function testidOf(el: Element): string | undefined {
    for (const a of TESTID_ATTRS) {
      const v = el.getAttribute(a);
      if (v) return v;
    }
    return undefined;
  }

  function directText(el: Element): string | undefined {
    let t = "";
    for (const n of Array.from(el.childNodes)) {
      if (n.nodeType === Node.TEXT_NODE) t += n.textContent ?? "";
    }
    t = t.replace(/\s+/g, " ").trim();
    if (!t) return undefined;
    return t.length > 80 ? t.slice(0, 80) + "\u2026" : t;
  }

  function walk(el: Element): SkelNode | null {
    if (budget-- <= 0) return null;
    if (IGNORE_TAGS.has(el.tagName)) return null;
    if (!visible(el)) return null;

    const node: SkelNode = { tag: el.tagName.toLowerCase(), children: [] };
    const role = el.getAttribute("role");
    if (role) node.role = role;
    const testid = testidOf(el);
    if (testid) node.testid = testid;
    const label =
      el.getAttribute("aria-label") ||
      el.getAttribute("placeholder") ||
      el.getAttribute("alt") ||
      undefined;
    if (label) node.label = label.replace(/\s+/g, " ").trim().slice(0, 80);
    const type = el.getAttribute("type");
    if (type) node.type = type;
    const text = directText(el);
    if (text) node.text = text;

    for (const child of Array.from(el.children)) {
      const c = walk(child);
      if (c) node.children.push(c);
    }
    return node;
  }

  const root = document.querySelector(focusSelector) ?? document.querySelector("main") ?? document.body;
  return root ? walk(root) : null;
}

/**
 * Flatten a skeleton into a multiset of stable per-node signatures. A signature
 * is the identity an agent would key off: testid first, else role+label/text,
 * else tag+type+label. This is what the structural differ compares.
 */
export function signatures(node: SkelNode | null): string[] {
  const out: string[] = [];
  function sig(n: SkelNode): string | null {
    if (n.testid) return `testid:${n.testid}`;
    if (n.role && (n.label || n.text)) return `role:${n.role}|${(n.label || n.text)!.toLowerCase()}`;
    if (n.role) return `role:${n.role}`;
    if ((n.tag === "input" || n.tag === "button" || n.tag === "a") && (n.label || n.text))
      return `${n.tag}:${(n.label || n.text)!.toLowerCase()}`;
    if (n.type) return `${n.tag}[${n.type}]`;
    return null;
  }
  function walk(n: SkelNode) {
    const s = sig(n);
    if (s) out.push(s);
    n.children.forEach(walk);
  }
  if (node) walk(node);
  return out;
}
