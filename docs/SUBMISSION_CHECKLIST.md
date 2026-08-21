# Submission Checklist

Date: 2026-08-21

This checklist records executed checks for the final interview delivery. It is not a placeholder checklist.

| Item | Result | Evidence |
| --- | --- | --- |
| Repository runnable | PASS | Local FastAPI and Vite servers started; browser health status connected. |
| Fresh clone | PASS | Isolated clone `a25e746` under `%TEMP%`; new `.venv`, `pip install -r requirements-dev.txt`, `npm.cmd ci`, build, 119 backend tests, and 5 Playwright browser tests passed. No existing project venv, `node_modules`, `dist`, database, or runtime cache was reused. |
| Frontend build | PASS | `npm.cmd run build`; TypeScript and Vite production build passed. |
| Backend tests | PASS | `119 passed` with `python -m pytest -q` from `backend/`. |
| Playwright | PASS | `5 passed`; cached Demo, no-key failure, bilingual persistence, and responsive checks. |
| Workout E2E | PASS | Live U.S. run `RUN-988362CE625A`: 250/250, 20 Topics, 26 Findings, 10 Requirements, 30 TestCases, 100% coverage, 0 hard failures. |
| Unknown input | PASS | Music CSV run `RUN-F347D369B442`: 24/24, four music Topics, four Findings, four Requirements, 16 TestCases, 100% coverage. |
| CSV | PASS | Music CSV E2E and sample import regression passed. |
| JSON | PASS | Mixed-language JSON run `RUN-AC28975293F5`: 24/24 and 100% coverage. |
| Mixed languages | PASS | English + Chinese Reviews retained original text; `zh-CN` output was verified independently from UI locale. |
| Conflicting evidence | PASS | Existing deterministic fixtures validate semantic conflict handling and `CONFLICTED` status without rating-only rules. |
| Insufficient evidence | PASS | Existing deterministic fixtures validate `INSUFFICIENT` handling and downstream blocking. |
| Model failure | PASS | Invalid key, timeout, invalid structured output, and provider failure tests preserve prior artifacts and create no fake result. |
| Cached demo | PASS | `cached_results/workout_demo.json`, API endpoint, and browser Demo flow validated with no API key. |
| No-key behavior | PASS | Backend returns actionable `LLM_NOT_CONFIGURED`; browser shows the error while keeping deterministic data and Demo usable. |
| Traceability | PASS | Workout and imported E2E runs report 100% overall coverage and zero hard failures; corruption injection is `VALIDATION_FAILED`. |
| Secret scan | PASS | Current repository and all reachable Git commits were scanned for API-key, Bearer credential, and private-key patterns; no secret was found. `.env` is ignored and untracked. |
| Git history | PASS | Incremental Phase 1-7 commits are preserved; generated/runtime artifacts are ignored and the final delivery worktree is clean. |
| README complete | PASS | Final Submission Guide plus original assignment background retained in `README.md`. |
| `.env.example` complete | PASS | Safe placeholders only; DeepSeek/API and local frontend/backend settings documented. |

## Commands

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm.cmd ci
npm.cmd run build
npm.cmd test
```
