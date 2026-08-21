# Final Acceptance Report

Date: 2026-08-21

## Decision

All Phase 7 hard gates passed. The final delivery candidate was cloned into an isolated `%TEMP%` directory and rebuilt without the existing project virtual environment, `node_modules`, `dist`, database, or runtime state. The current tree and complete reachable Git history were also scanned for credential patterns with no secret found.

## Acceptance matrix

| Test | Expected | Actual | Result | Evidence |
| --- | --- | --- | --- | --- |
| Data layer | App Store, CSV, JSON normalize into common Reviews; cleaning is deterministic. | U.S. App Store, Music CSV, mixed JSON, dirty/duplicate, and sample import tests passed. | PASS | `backend/tests`, `RUN-988362CE625A`, `RUN-F347D369B442`, `RUN-AC28975293F5`. |
| Runtime AI | New live runs call configured DeepSeek, use structured output, batch, goal, and output language. | Workout and imported runs show `deepseek / deepseek-v4-flash`, new analysis timestamps, bounded batches, and no cached label. | PASS | Runtime run metadata and `backend/scripts/final_e2e_smoke.py`. |
| Evidence grounding | Findings use current-run Review IDs, semantic stances, sufficiency, conflicts, confidence, uncertainty, and limitations. | Phase 4 regression plus full pipeline runs passed; unknown/cross-run IDs and lineage violations are rejected or repaired within source lineage. | PASS | `docs/PHASE4_ACCEPTANCE.md`, `RUN-988362CE625A` audit revisions. |
| Product planning | Requirements, VersionPlan, PRD, and TestCases remain grounded and inherited. | Workout produced 10 Requirements, 2 versions, and 30 TestCases; imported Music produced 4 Requirements and 16 TestCases. | PASS | `docs/PHASE5_ACCEPTANCE.md` and final run artifacts. |
| Test generation | TestCases link to Requirements and inherited Review evidence. | Final traceability reports exact inherited evidence and zero hard failures. | PASS | Traceability APIs and backend tests. |
| Traceability | Forward/reverse chain and coverage are persisted; structural failures block completion. | Workout: 100% overall coverage, 0 hard failures. Corruption injection yields `VALIDATION_FAILED`. | PASS | `docs/PHASE6_ACCEPTANCE.md`, `test_final_traceability_failure_sets_validation_failed`. |
| Unknown input | Unseen compatible dataset produces domain-specific Topics and full downstream artifacts. | Music CSV produced offline playback, lyrics, collaborative playlist, and recommendation Topics without Workout taxonomy. | PASS | `RUN-F347D369B442`. |
| Failure handling | Collection/model/structured-output/traceability failures preserve prior work and never fabricate final artifacts. | App Store failure, no-key, invalid key, timeout, provider error, invalid output, and final validation injection passed. | PASS | Backend regression suite and Playwright no-key scenario. |
| Local run | Fresh checkout installs and starts using documented commands. | Isolated clone `a25e746` created a new Python venv, installed declared dependencies, ran 119 tests, rebuilt via `npm ci`, passed production build, and passed 5 browser tests against fresh FastAPI/Vite servers. | PASS | `%TEMP%/app-review-insights-fresh-20260821-102514`, `docs/SUBMISSION_CHECKLIST.md`. |
| Documentation | README explains setup, data, AI boundaries, grounding, tracing, Demo, tests, and limitations. | Final Submission Guide added without removing the original assignment README. | PASS | `README.md`. |
| Security | Secrets are absent from current tracked files and Git history; generated files are ignored. | Current repository and all reachable commits returned no API-key, Bearer credential, or private-key pattern hits. `.env`, virtual environments, dependencies, builds, local databases, logs, uploads, and Playwright artifacts are ignored. | PASS | `git check-ignore`, current-tree scan, full-history `git grep`. |

## Real E2E results

### Workout for Women, live U.S. App Store

`RUN-988362CE625A` used the official U.S. URL and live Apple source. It collected and analyzed 250/250 Reviews in 10 semantic batches using DeepSeek. The result contained 20 consolidated Topics, 26 validated Findings, 10 Requirements, 2 versions, and 30 TestCases. Final traceability coverage was `1.0`, hard failures were `0`, and the run status was `COMPLETED_WITH_WARNINGS` because real source limitations and artifact revisions remain visible.

### Unknown Music CSV

`RUN-F347D369B442` analyzed 24/24 imported Reviews with `output_language=en-US`. It produced four domain-specific Topics, four Findings, four Requirements, two versions, and 16 TestCases. Coverage was `1.0` with zero hard failures. The result was not cached and used the configured runtime provider.

### Mixed-language JSON

`RUN-AC28975293F5` analyzed 24/24 English + Chinese Reviews with `output_language=zh-CN`. The source texts were byte-for-byte unchanged after the pipeline. It produced 18 Findings, 3 eligible Requirements, 2 versions, and 12 TestCases with `1.0` coverage and zero hard failures. The acceptance script verified Chinese output independently of the UI locale.

## Failure and safety results

- No `LLM_API_KEY`: local `LLM_NOT_CONFIGURED`, no provider call and no fake semantic result; cached Demo remains available.
- Invalid API key, timeout, provider failure, and invalid structured output: finite retries, preserved cleaned/validated upstream data, explicit `FAILED`, no fabricated downstream artifacts.
- Invalid/cross-run Review IDs: rejected before semantic validation or corrected only by removing the invalid reference and carrying forward the original valid source candidate.
- Final traceability corruption: `VALIDATION_FAILED`, errors and prior artifacts preserved.

## Browser and screenshots

The repository Playwright suite completed 5 tests with zero browser console errors. It validated the cached Demo, bilingual switching and refresh persistence, no-key failure, and 1366x768, 1440x900, 1920x1080, and 390x844 responsive behavior. Screenshots are intentionally ignored runtime artifacts:

```text
output/playwright/phase7/phase7-1440x900-overview.png
output/playwright/phase7/phase7-1440x900-findings.png
output/playwright/phase7/phase7-1440x900-requirements.png
output/playwright/phase7/phase7-1440x900-prd.png
output/playwright/phase7/phase7-1440x900-traceability.png
output/playwright/phase7/phase7-1366x768-traceability.png
output/playwright/phase7/phase7-1920x1080-traceability.png
output/playwright/phase7/phase7-390x844-traceability.png
output/playwright/phase7/phase7-no-key-failure.png
```

## Verified commands

```text
Backend: 119 passed
Frontend: npm run build passed
Playwright: 5 passed
Fresh clone: PASS
Secret scan: PASS
```

## Remaining limitations

The U.S. customer-review feed is an undocumented bounded recent feed. DeepSeek availability and quota are external dependencies for live analysis. The one-week architecture intentionally uses one FastAPI process, one in-process worker path, SQLite, polling, and no authentication or distributed infrastructure. Runtime semantic judgments remain probabilistic even though all identifiers, evidence inheritance, artifact dispositions, and traceability facts are deterministic.
