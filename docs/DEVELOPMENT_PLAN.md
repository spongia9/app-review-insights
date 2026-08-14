# App Review Insights — Development Plan

## 1. Delivery Objective

Deliver a complete, locally runnable one-week interview project that converts authentic App Store or imported reviews into evidence-grounded Findings, Requirements, a VersionPlan, a structured PRD, and TestCases with deterministic end-to-end traceability.

This plan is subordinate to `README.md`, `REQUIREMENTS.md`, `ARCHITECTURE.md`, and `AGENTS.md`. If implementation pressure creates a conflict, mandatory grounding, validation, and traceability take priority over polish or optional features.

## 2. Non-Negotiable Baseline

- Runtime LLM semantic discovery; no fixed-keyword or example-app taxonomy as the core semantic layer.
- U.S. storefront for compliant live App Store collection.
- App Store URL, CSV, and JSON converge on one Review model.
- Every persisted domain/artifact object is scoped by `analysis_run_id`; cross-run references are forbidden.
- Every major Finding receives deterministic ID validation and mandatory semantic support validation.
- Requirement and TestCase Review evidence is inherited from validated upstream artifacts.
- Structured PRD is validated before deterministic Markdown rendering.
- Traceability is calculated deterministically and gates run completion.
- Single-process, single worker background execution with stage-boundary persistence and frontend polling.
- Cached/demo provenance and partial-analysis limitations are visible.

Default upload safety limits are 10 MiB and 10,000 records. Over-limit input is rejected without silent truncation.

## 3. Scope Guardrails

Do not add this week:

```text
Redis
Celery
RAG
LangGraph
Multi-Agent runtime
Vector Database
Microservices
Authentication / RBAC
WebSocket
complex production deployment
```

Defer until mandatory functionality is stable:

```text
complex charting and visualization
advanced export
manual Requirement editing
advanced filters
multiple LLM providers
ORM or complex migration tooling
large frontend component test suites
```

## 4. Phase Plan and Done Criteria

### Phase 0.5 — Specification Finalization and Git Baseline

Scope:

- Align requirements, architecture, agent rules, and this development plan.
- Define run scope, provenance, import contract, evidence semantics, inheritance, coverage, structured PRD, transparency, audit persistence, execution strategy, and upload safety.
- Initialize Git and establish ignore rules.

Done Criteria:

- `REQUIREMENTS.md`, `ARCHITECTURE.md`, `AGENTS.md`, and this document use consistent terminology and rules.
- Original company `README.md` remains present and unchanged.
- `.gitignore` excludes secrets, dependencies, caches, build output, local databases, and temporary artifacts.
- Git repository is initialized at the project root.
- Specification baseline is committed with a meaningful commit.
- No frontend, backend, provider, LLM, or business logic has been created.

### Phase 1 — Skeleton

Scope:

- React + TypeScript + Vite + Tailwind scaffold.
- FastAPI scaffold.
- Pydantic boundary/domain models and enums.
- SQLite initialization, configuration, logging, CORS, and health API.
- Frontend/backend connectivity and test setup.

Done Criteria:

- Backend starts locally and health endpoint succeeds.
- Frontend displays backend health state.
- Models include `analysis_run_id` where required and use the defined statuses/dispositions.
- Configuration uses environment variables and `.env.example` contains no secrets.
- Relevant backend tests pass and frontend production build passes.
- No semantic analysis or product-output business logic exists yet.

### Phase 2 — Data

Scope:

- U.S. App Store URL parsing and provider acquisition.
- CSV/JSON contract implementation.
- Upload byte/record enforcement.
- Common Review normalization, deterministic cleaning, stable IDs, and deduplication.
- Raw, invalid, duplicate, and clean counts plus provenance/limitations.

Done Criteria:

- App Store, CSV, and JSON enter the same run-scoped Review pipeline.
- Live App Store results record and verify U.S. storefront provenance or are marked non-compliant with warning.
- Invalid rows are reported without fabricated replacements; malformed/empty/over-limit input fails clearly.
- URL, CSV, JSON, normalization, stable-ID, deduplication, upload-limit, and run-scope tests pass.
- Relevant backend tests pass; frontend build passes if changed.
- PRD and semantic business logic have not started.

### Phase 3 — Semantic Analysis

Scope:

- One real LLM provider behind a small internal interface.
- Structured prompt/output schemas.
- Bounded batch topic discovery and cross-batch consolidation.
- Hierarchical consolidation groups with persisted round checkpoints and consolidation-only resume.
- Safe provider diagnostics for truncation, empty output, malformed JSON, and schema mismatch.
- Structured Finding drafts referencing current-run Review IDs.
- Goal-aware analysis and limited retries for invalid output/failure.

Done Criteria:

- Topics change meaningfully for unseen datasets and are not tied to Workout for Women.
- Core topic discovery executes at runtime through the configured model.
- Model outputs validate through Pydantic and only current-run Review IDs are accepted.
- `total_review_count`, `analyzed_review_count`, `sampling_strategy`, and `batch_count` are stored.
- Topic/Finding drafts are persisted as audit artifacts.
- Large multi-batch inputs do not depend on one unbounded consolidation response, and compatible failures resume without repeating completed batch analysis.
- Mocked deterministic tests pass; a configured real-provider smoke run is documented when credentials/network are available.

### Phase 4 — Evidence

Scope:

- Deterministic run-scoped ID validation.
- Mandatory semantic support/conflict/ambiguity/irrelevance validation.
- Transparent evidence-strength heuristic and fixed Finding statuses.
- Finding acceptance, revision, rejection, and assumption audit behavior.

Done Criteria:

- Unknown and cross-run Review IDs are rejected.
- Supporting/conflicting sets are unique, disjoint, and counts are code-derived.
- A valid ID whose text does not support a claim cannot produce `SUPPORTED`.
- `SUPPORTED`, `WEAK`, `CONFLICTED`, `INSUFFICIENT`, and `UNSUPPORTED` scenarios are tested.
- Unsupported Findings do not silently reach Requirement generation.
- Evidence validation artifacts and revision reasons are persisted.
- Relevant backend tests pass.

### Phase 5 — Product Output

Scope:

- Requirement drafts and deterministic evidence inheritance.
- VersionPlan.
- Structured PRD, validation, and deterministic Markdown rendering.
- TestCase drafts and inherited evidence chain.
- Validation dispositions and deterministic coverage calculation.

Done Criteria:

- Non-assumption Requirements reference current-run validated Findings and derived Review evidence.
- `Requirement.review_ids` is deterministically inherited from validated Finding support evidence; any stored subset is validated against that allowed set.
- TestCases trace through Requirement and Finding to current-run Reviews.
- Stored Review subsets satisfy the configured inheritance rule.
- Rejected artifacts remain auditable but do not enter final deliverables.
- Final PRD contains only validated facts, explicit assumptions, and known limitations.
- All hard-failure cases are detected; empty coverage denominators report `N/A`.
- Finding evidence coverage, Requirement traceability coverage, TestCase traceability coverage, and Overall traceability coverage are all calculated from current-run non-rejected artifacts.
- `COMPLETED` requires zero hard failures and 100% applicable required coverage; warning cases produce `WARNING`.
- Relevant backend tests pass.

### Phase 6 — UI Completion

Scope:

- New Analysis for App Store/CSV/JSON plus analysis goal.
- Polling progress and intermediate stage results.
- Reviews, Topics, Findings/Evidence, Requirements, VersionPlan, PRD, TestCases, and Traceability views.
- Warnings, errors, revisions, limitations, partial-analysis counts, and cached/demo labels.

Done Criteria:

- All three source types can start a run through the UI.
- Users can navigate Finding -> Review and TestCase -> Requirement -> Finding -> Review.
- Major intermediate audit artifacts and validation outcomes are inspectable where useful.
- Cached/demo content is unmistakably labeled and provenance is visible.
- Partial/sampled analysis never appears to cover all Reviews.
- Failure and insufficient-evidence states remain usable and truthful.
- Frontend production build and relevant backend tests pass; critical flow receives a smoke test.

### Phase 7 — Stabilization

Scope:

- Robustness scenarios, bug fixes, authentic sample data, cached results, documentation, and demo rehearsal.
- No major new architecture.

Done Criteria:

- Normal English, mixed-language, duplicate, conflicting, sparse, invalid-ID, model-failure, collection-failure, unseen-input, upload-limit, and cross-run scenarios are tested.
- Cached/sample provenance is complete and clearly labeled.
- README documents setup, data source, AI provider/model/prompts, structured output, retries, grounding, limitations, offline demo, and local run commands.
- Full backend suite passes and frontend production build passes.
- `.env.example` exists without secrets and clean setup instructions work.
- Git history is incremental and meaningful.

## 5. Pipeline Completion Gates

Persist each stage output before advancing `last_successful_stage`. A model or collection failure preserves already committed deterministic/intermediate results.

Hard failures include unknown/cross-run references, broken evidence inheritance, count/list inconsistency, overlapping support/conflict evidence, unlabeled unsupported final claims, and unvalidated PRD facts.

The required validation audit artifacts cover topic draft, finding draft, evidence validation, requirement draft/revision, structured PRD draft, test case draft, and the final validation audit.

Warnings include weak/conflicted/insufficient evidence, explicit assumptions, partial analysis, sampling, rejected import rows, provider limitations, and planned Requirements without adequate test coverage.

Run status values are:

```text
PENDING
RUNNING
COMPLETED
WARNING
FAILED
```

## 6. Required Phase Report

Before declaring any phase complete, report:

```text
What changed
Files changed
Tests run
Build result
Known limitations
Remaining work
```

Do not claim a phase is complete when required tests or builds fail.
