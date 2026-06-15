/**
 * Workflows are scripted interactions, not single screens. Each step is an
 * action driven by Playwright; the tracer snapshots the observed subtree
 * before/after every step so we can diff the *transitions* (e.g. which fields
 * appear when work type changes Task -> Story) between real Jira and JP.
 *
 * Selectors are deliberately given as candidate lists: real Jira's markup is
 * obfuscated and version-dependent, so we try several and let a step fail
 * gracefully (recorded as `ok: false`) rather than aborting the trace — a
 * failed step is itself a signal.
 */
import type { Page } from "playwright";

import { config } from "../config.ts";
import { clickAny, fillAny } from "./util.ts";

export interface WorkflowStep {
  label: string;
  run: (page: Page) => Promise<void>;
}

export interface WorkflowTarget {
  url: (base: string) => string;
  /** Subtree whose field set we snapshot for per-step deltas. */
  observe: string;
  steps: WorkflowStep[];
}

export interface Workflow {
  name: string;
  jira: WorkflowTarget;
  jp: WorkflowTarget;
}

/** Pick an option containing the given text from any open listbox/menu. */
async function pickOption(page: Page, text: string): Promise<void> {
  await clickAny(page, [
    `[role="option"]:has-text("${text}")`,
    `[role="menuitem"]:has-text("${text}")`,
    `li:has-text("${text}")`,
    `text="${text}"`,
  ]);
}

export const workflows: Workflow[] = [
  {
    name: "create-issue",
    jira: {
      url: (base) => `${base}/jira/your-work`,
      observe: '[role="dialog"]',
      steps: [
        {
          label: "open-modal",
          run: async (page) => {
            await clickAny(page, [
              '[data-testid="atlassian-navigation--create-button"]',
              'button:has-text("Create")',
              'role=button[name="Create"]',
            ]);
            await page.locator('[role="dialog"]').first().waitFor({ state: "visible", timeout: 15000 });
          },
        },
        {
          label: "work-type-story",
          run: async (page) => {
            // Jira's work-type picker is a react-select with a dynamic id
            // (`type-picker-<hash>`). Open it, type to filter, pick "Story".
            const input = page.locator('[id^="type-picker-"], #issuetype-field').first();
            await input.click({ force: true, timeout: 8000 });
            await input.pressSequentially("Story", { delay: 20 });
            await page.waitForTimeout(500);
            try {
              await pickOption(page, "Story");
            } catch {
              await input.press("Enter");
            }
          },
        },
        {
          label: "fill-summary",
          run: async (page) => {
            await fillAny(
              page,
              [
                '[data-testid="issue-create.ui.modal.create-form.layout-renderer.field-renderer.field.summary"] input',
                "#summary-field",
                '[name="summary"]',
              ],
              "Ranger parity probe",
            );
          },
        },
      ],
    },
    jp: {
      url: (base) => `${base}/`,
      observe: '[data-testid="issue-create.ui.modal"]',
      steps: [
        {
          label: "open-modal",
          run: async (page) => {
            // Retry the click until the modal mounts (next dev hydration race).
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
        },
        {
          label: "work-type-story",
          run: async (page) => {
            await clickAny(page, [
              '[data-testid="issue-create.ui.modal.field.issuetype.trigger"]',
              '[data-testid="issue-create.ui.modal.field.issuetype"] [role="combobox"]',
              '[data-testid="issue-create.ui.modal.field.issuetype"] button',
            ]);
            await pickOption(page, "Story");
          },
        },
        {
          label: "fill-summary",
          run: async (page) => {
            await fillAny(
              page,
              ['[data-testid="issue-create.ui.modal.field.summary.input"]', '[name="summary"]'],
              "Ranger parity probe",
            );
          },
        },
      ],
    },
  },

  {
    // Simple board workflow: open the board, then open the first card. The tracer
    // snapshots `main` before/after each step, so the board -> issue-detail
    // transition (which fields appear when a card is opened) is captured and
    // diffed between real Jira and JP.
    name: "board",
    jira: {
      url: (base) => `${base}${config.jira.boardPath}`,
      observe: "main",
      steps: [
        {
          label: "open-card",
          run: async (page) => {
            await clickAny(page, [
              '[data-testid="platform-board-kit.ui.card.card"]',
              '[data-testid*="card-container"] a',
              '[data-testid*="card"]',
              'a[href*="selectedIssue="]',
            ]);
            await page.waitForTimeout(1500);
          },
        },
      ],
    },
    jp: {
      url: (base) => `${base}/board?key=${config.jp.boardKey}`,
      observe: "main",
      steps: [
        {
          label: "open-card",
          run: async (page) => {
            await clickAny(page, ['main a[href^="/issue?id="]', 'a[href^="/issue?id="]']);
            await page.waitForTimeout(1500);
          },
        },
      ],
    },
  },
];
