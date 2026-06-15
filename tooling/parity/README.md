# Parity tooling + Ranger

A differential parity oracle between **real Atlassian Jira** and **Jirassic Park (JP)**, and **Ranger** — an autonomous loop that closes the gap.

```
capture (Playwright)  ->  detect (Opus, multimodal)  ->  patch (Cursor SDK)
   ^                                                          |
   +------------------  judge + pixel guardrail  <------------+
```

Real Jira is captured **once** into committed golden fixtures (the frozen target). The loop only re-captures JP, so the only thing changing between iterations is our own code. A screen passes when the Opus judge accepts **and** the deterministic focus-region pixel mismatch hasn't regressed past baseline. Patches land on a dedicated `ranger/<ts>` git branch for human review — never an auto-merge.

## Setup

```bash
npm install
npx playwright install chromium
```

Secrets live in the **repo-root `.env`** (gitignored):

```
CURSOR_API_KEY=...        # patch step (Cursor SDK)
ANTHROPIC_API_KEY=...     # detect + judge steps (Opus)
# optional overrides:
# RANGER_DETECT_MODEL / RANGER_JUDGE_MODEL  (default: claude-opus-4-6)
# RANGER_PATCH_MODEL                         (default: composer-2.5)
# RANGER_MAX_ITERS                           (default: 4)
# JIRA_BASE_URL / JIRA_ISSUE_KEY / JP_BASE_URL / JP_TOKEN / JP_ISSUE_KEY
```

### Serving JP so the loop sees patches

`:8080` is the FastAPI backend serving a **static Next.js export** (baked into the container). Patches to `frontend/` source won't show up there. For the loop to converge, run the **hot-reloading dev stack** and point Ranger at it with `--jp-dev`:

```bash
make dev-backend                                          # uvicorn on :8080
cd frontend && NEXT_PUBLIC_API_BASE=http://localhost:8080 npm run dev   # next dev on :3000
```

`next dev` recompiles on each fresh navigation, and after every patch Ranger waits for the server to answer again (covering both the recompile and a `uvicorn --reload` restart) before recapturing — so the judge always sees the latest UI.

## Commands

```bash
npm run login            # one-time interactive login to real Jira (saves .auth/)
npm run ranger:fixtures  # one-time: capture real Jira goldens into fixtures/ (commit them)
npm run ranger -- --jp-dev                       # full autonomous loop against the dev server (:3000)
npm run ranger -- --jp-dev --pr                  # ...and open a PR with before/after screenshots
npm run ranger -- --jp-dev --screen create-issue --max-iters 4
npm run ranger -- --detect-only                  # capture + detect + report, no patching
npm run ranger -- --no-branch                    # stay on the current git branch
npm run ranger -- --jp-url http://localhost:3000 # explicit JP base URL
npm run run              # the older one-shot deterministic diff report (out/index.html)
```

### `--pr`

After the loop makes at least one patch, `--pr` takes a fresh post-patch screenshot, commits the patch + before/after/target images to `tooling/parity/pr-assets/<run>/`, pushes the `ranger/<ts>` branch, and opens a PR whose body embeds those images (via raw URLs) alongside the discrepancy list. Requires the GitHub CLI: `brew install gh && gh auth login`. Without it, the branch is still pushed and the PR body is saved to a temp file for manual creation.

## Layout

| File | Role |
| --- | --- |
| `src/screens.ts` | screens to compare (visual) + how to navigate to each |
| `src/workflows.ts` | scripted interactions (behavioral), e.g. create-issue Task→Story |
| `src/recorder.ts` | screenshot + DOM + network capture |
| `src/trace.ts` | mechanical per-step action trace (field deltas + requests) |
| `src/detect.ts` | Opus multimodal → structured discrepancy list |
| `src/judge.ts` | Opus semantic verdict (paired with the pixel guardrail) |
| `src/patch.ts` | Cursor SDK local coding agent applies the fix |
| `src/ranger.ts` | the orchestrator / loop |
| `fixtures/` | committed real-Jira goldens (the frozen target) |
| `out/` | per-run artifacts (gitignored) |

Detection and the judge are non-reproducible by nature; that's acceptable because this is a dev-time loop gated by the deterministic pixel guardrail, not a training reward.
