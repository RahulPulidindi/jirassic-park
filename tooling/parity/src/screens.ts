import type { Page } from "playwright";

import { config } from "../config.ts";

/**
 * A screen knows, per target, how to navigate to the state we want to compare
 * and which selector frames the "focused component" (used for the tight visual
 * diff). `navigate` should leave the page settled on the state to capture.
 */
export interface ScreenTarget {
  url: (base: string) => string;
  /** Optional interaction to reach the state (e.g. open the create modal). */
  reach?: (page: Page) => Promise<void>;
  /** Selector for the focused component; falls back to <main> / body. */
  focus: string;
}

export interface Screen {
  name: string;
  jira: ScreenTarget;
  jp: ScreenTarget;
}

/** Click the first match of several candidate selectors; ignore misses. */
async function clickAny(page: Page, selectors: string[], timeout = 8000): Promise<void> {
  for (const sel of selectors) {
    const loc = page.locator(sel).first();
    try {
      await loc.waitFor({ state: "visible", timeout });
      await loc.click();
      return;
    } catch {
      /* try next */
    }
  }
  throw new Error(`None of the candidate selectors were clickable: ${selectors.join(", ")}`);
}

export const screens: Screen[] = [
  {
    name: "create-issue",
    jira: {
      // `base` is supplied by the caller (jira base for goldens) — never hardcode
      // it, or the --jp-dev / --jp-url override silently navigates the wrong host.
      url: (base) => `${base}/jira/your-work`,
      reach: async (page) => {
        await clickAny(page, [
          '[data-testid="atlassian-navigation--create-button"]',
          'button:has-text("Create")',
          'role=button[name="Create"]',
        ]);
        await page.locator('[role="dialog"]').first().waitFor({ state: "visible", timeout: 15000 });
      },
      focus: '[role="dialog"]',
    },
    jp: {
      url: (base) => `${base}/`,
      reach: async (page) => {
        // The button is in the DOM before React hydrates, so the first click can
        // be dropped. Retry until the modal actually appears.
        const btn = page.locator('[data-testid="navigation-apps.action-buttons.create.button"]').first();
        const modal = page.locator('[data-testid="issue-create.ui.modal"]').first();
        await btn.waitFor({ state: "visible", timeout: 15000 });
        for (let i = 0; i < 4; i++) {
          await btn.click({ timeout: 5000 }).catch(() => {});
          try {
            await modal.waitFor({ state: "visible", timeout: 5000 });
            return;
          } catch {
            await page.waitForTimeout(1000);
          }
        }
        throw new Error("create modal did not open after retrying the Create button");
      },
      focus: '[data-testid="issue-create.ui.modal"]',
    },
  },

  {
    name: "issue-detail",
    jira: {
      url: (base) => `${base}/browse/${config.jira.issueKey}`,
      focus: '[data-testid="issue.views.issue-base"], main',
    },
    jp: {
      url: (base) => `${base}/issue?id=${config.jp.issueKey}`,
      focus: '[data-testid="issue.views.issue-base"], main',
    },
  },

  {
    name: "board",
    jira: {
      url: (base) => `${base}${config.jira.boardPath}`,
      focus: "main",
    },
    jp: {
      url: (base) => `${base}/board?key=${config.jp.boardKey}`,
      focus: "main",
    },
  },

  {
    name: "for-you",
    jira: {
      url: (base) => `${base}/jira/for-you`,
      focus: "main",
    },
    jp: {
      url: (base) => `${base}/`,
      focus: "main",
    },
  },
];
