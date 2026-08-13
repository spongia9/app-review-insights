# AGENTS.md — Codex Instructions for App Review Insights

## 1. Purpose

This file contains persistent repository-level instructions for Codex and any other coding agent working on this project.

Read this file before making implementation decisions.

The project is a one-week interview assignment.

The goal is to deliver a complete and locally runnable application, not a commercial-scale platform.

---

# 2. Core Project Goal

Build an AI-driven App Store review analysis and product planning application.

The central domain chain is:

```text
Review
  ↓
Finding
  ↓
Requirement
  ↓
TestCase
```

This chain must remain traceable throughout the application.

---

# 3. Fixed Technology Stack

Unless explicitly instructed otherwise, use:

## Frontend

```text
React
TypeScript
Vite
Tailwind CSS
```

Use one lightweight chart library only when needed.

## Backend

```text
Python
FastAPI
Pydantic
Pandas
httpx
SQLite
Pytest
```

## AI

Use a runtime LLM through an internal provider abstraction.

One real provider is sufficient for the interview version.

---

# 4. Mandatory Product Requirements

The application must support:

```text
U.S. App Store URL
CSV import
JSON import
Analysis Goal
Unknown / unseen compatible input
Review cleaning
Deduplication
Dynamic model-driven topic discovery
Evidence-grounded findings
Conflicting evidence
Insufficient evidence
Requirements
Version planning
PRD
Test cases
Traceability validation
Progress UI
Intermediate results
Failure handling
Sample/cached review capability
```

---

# 5. Mandatory AI Rules

## Rule AI-1

Core semantic analysis must be model-driven at runtime.

Using Codex to generate project source code does not satisfy the application AI requirement.

---

## Rule AI-2

Do not implement the core semantic layer using only:

```text
fixed keyword mappings
regex
lookup tables
hard-coded categories
app-specific taxonomy
```

---

## Rule AI-3

General labels such as:

```text
Bug
Feature Request
Performance
Usability
Subscription
```

may exist as optional secondary metadata.

They must not replace dynamic semantic topic discovery.

---

## Rule AI-4

Prefer structured model output validated by Pydantic.

Do not build core application logic around parsing uncontrolled prose.

---

# 6. Evidence Rules

## Rule E-1

Never fabricate reviews.

---

## Rule E-2

Never fabricate review IDs.

---

## Rule E-3

Every major finding must preserve source evidence.

At minimum:

```text
supporting_review_ids
support_count
```

When relevant:

```text
conflicting_review_ids
conflict_count
uncertainty
limitations
```

---

## Rule E-4

Every model-generated review reference must be checked against the actual current analysis dataset.

Unknown review IDs must be rejected.

---

## Rule E-5

Unsupported conclusions must not silently enter the final PRD.

They must be one of:

```text
removed
revised
explicitly marked as assumption
explicitly marked unsupported
```

---

## Rule E-6

Evidence status should support at least:

```text
SUPPORTED
WEAK
CONFLICTED
INSUFFICIENT
UNSUPPORTED
```

Equivalent naming is acceptable if semantics remain clear.

## Rule E-7 — Mandatory Semantic Support Validation

Every major Finding must pass both deterministic ID/run-scope validation and semantic support validation. The existence of a Review ID does not prove that its text supports the Finding claim.

Semantic validation must distinguish supporting, conflicting, ambiguous, and irrelevant evidence. Code must calculate counts, ratios, and the documented evidence-strength heuristic; do not treat an unverified model confidence value as evidence.

Evidence status semantics are fixed:

```text
SUPPORTED    sufficient valid semantic support with no material unresolved conflict
WEAK         some valid support, but weak volume, clarity, or representativeness
CONFLICTED   material valid evidence supports opposing conclusions
INSUFFICIENT relevant evidence is too sparse or ambiguous
UNSUPPORTED  evidence is invalid, irrelevant, or does not support the claim
```

## Rule E-8 — Generated Artifact Disposition

Every AI-generated artifact that can enter a final deliverable, including each Requirement, VersionPlan item, PRD section, and TestCase, must receive one validation disposition:

```text
ACCEPTED
REVISED
REJECTED
ASSUMPTION
```

Rejected artifacts remain in the validation audit but do not enter final deliverables. Revised artifacts retain their reason and original relationship. Assumptions must be visibly labeled and never presented or counted as supported facts.

---

# 7. Traceability Rules

The following relationships are mandatory:

```text
Finding → Review
Requirement → Finding
Requirement → Review
TestCase → Requirement
TestCase → Review
```

Before an analysis run is considered complete, deterministic validation must check these relationships.

Do not rely only on an LLM to claim the chain is valid.

## Rule T-1 — Run Scope

Every persisted `Review`, `Finding`, `Requirement`, `TestCase`, `VersionPlan`, `PRDArtifact`, and `ValidationResult` must include `analysis_run_id`.

All reference and Review ID validation must be constrained to the current run. Cross-run references are hard failures even when the referenced identifier exists globally.

## Rule T-2 — Evidence Inheritance

`Requirement.review_ids` must be derived from the valid `supporting_review_ids` of its referenced Findings. The model must not freely invent Requirement Review evidence.

`TestCase.source_review_ids` must be inherited through:

```text
TestCase -> Requirement -> Finding -> Review
```

Stored subsets must be non-empty subsets of the upstream allowed evidence set. Validators must enforce the configured subset/equality rule.

## Rule T-3 — Coverage and Completion

Calculate Finding evidence coverage, Requirement traceability coverage, TestCase traceability coverage, and overall traceability coverage over current-run, non-rejected artifacts. Empty denominators are `N/A`.

Unknown/cross-run references, broken inheritance, count/list mismatches, overlapping support/conflict evidence, or unlabeled unsupported final claims are hard failures. Weak/conflicted/insufficient evidence, explicit assumptions, partial analysis, rejected rows, provider limitations, and incomplete Requirement test coverage are warnings.

`COMPLETED` requires zero hard failures and 100% for every applicable required coverage metric.

---

# 8. Data Source Rules

All review providers must normalize into the same `Review` domain model.

Expected providers:

```text
AppStoreProvider
CSVProvider
JSONProvider
```

Downstream pipeline logic must not depend on source-specific schemas.

## U.S. Storefront Provenance

`AppStoreProvider` must explicitly use the U.S. storefront and save `source`, `storefront`, `collection_time`, and `source_limitations`. If U.S. provenance cannot be confirmed, do not label the result as compliant live App Store collection.

## Import Contract and Safety

CSV and JSON must use the canonical contract defined in `REQUIREMENTS.md`. `text` is required; documented aliases are allowed; invalid rows are reported; malformed files or zero valid rows fail explicitly. Defaults are a 10 MiB file limit and 10,000 parsed records. Reject over-limit input without silent truncation. All valid input normalizes to the common `Review` model.

---

# 9. Cleaning Rules

Cleaning must be deterministic.

Expected responsibilities:

```text
empty review handling
deduplication
rating normalization
date normalization
version normalization
stable internal review ID assignment
```

Do not use an LLM for basic deterministic normalization.

---

# 10. Pipeline Rules

The recommended pipeline order is:

```text
1. Scope Resolution
2. Data Acquisition
3. Cleaning & Normalization
4. Semantic Topic Discovery
5. Finding Consolidation
6. Evidence Evaluation
7. Requirement Generation
8. Version Planning
9. PRD Generation
10. Test Case Generation
11. Traceability Validation
```

Do not generate requirements before evidence evaluation unless explicitly implementing a draft/revision workflow.

When the Review set exceeds the configured model context strategy, use bounded batches followed by consolidation. Persist `total_review_count`, `analyzed_review_count`, `sampling_strategy`, and `batch_count`. Any sampling or truncation must be visible as a limitation.

The pipeline must preserve run-scoped intermediate audit artifacts for topic draft, finding draft, evidence validation, requirement draft/revision, structured PRD draft, test case draft, and validation audit.

PRD generation must follow:

```text
Structured PRD Model -> Validation -> Deterministic Markdown Renderer
```

PRD facts may come only from validated Findings, validated Requirements, the VersionPlan, explicit assumptions, and known limitations.

---

# 11. Architecture Constraints

Keep the one-week architecture simple.

Use:

```text
React frontend
FastAPI backend
SQLite persistence
HTTP API
frontend polling for progress
```

Do not introduce infrastructure unless a demonstrated requirement demands it.

---

# 12. Explicitly Disallowed Scope Expansion

Do not add the following unless the user explicitly requests them after mandatory functionality is complete:

```text
authentication
user accounts
RBAC
Redis
Celery
Kafka
RabbitMQ
Kubernetes
microservices
vector database
RAG
LangGraph
CrewAI
AutoGen
mandatory multi-agent architecture
complex production deployment
billing
mobile applications
WebSocket
```

Also defer until mandatory functionality is stable:

```text
complex charting and visualization
advanced export
manual Requirement editing
advanced filters
multiple LLM providers
ORM or complex migration tooling
large frontend component test suites
```

---

# 13. Coding Rules

## 13.1 Keep Modules Focused

Prefer clear modules for:

```text
providers
cleaning
LLM
findings
evidence
requirements
version planning
PRD
test cases
validation
```

Avoid giant files.

---

## 13.2 Avoid Premature Abstraction

Do not create abstraction layers that are not used by the one-week implementation.

Examples to avoid:

```text
complex event buses
generic plugin systems
repository factories
multi-database adapters
distributed orchestration abstractions
```

---

## 13.3 Type Boundaries

Use Pydantic models for backend API/domain boundaries.

Use TypeScript interfaces/types on the frontend.

Keep backend and frontend field names aligned.

---

## 13.4 Configuration

Secrets must come from environment variables.

Never commit:

```text
API keys
tokens
credentials
```

Provide:

```text
.env.example
```

---

# 14. Testing Rules

Before declaring any development phase complete:

1. run relevant backend tests;
2. fix test failures;
3. run frontend production build if frontend code changed;
4. fix build errors;
5. inspect changed files;
6. verify no unrelated modules were modified unnecessarily.

Recommended commands may include:

```bash
pytest
npm run build
```

Use the actual repository commands once configured.

---

# 15. Minimum Test Coverage Areas

Prioritize tests for:

```text
App Store URL parsing
CSV import
JSON import
review normalization
deduplication
invalid review ID rejection
finding evidence validation
requirement source validation
test case source validation
traceability coverage
pipeline failure states
```

Mock external LLM/network calls in deterministic automated tests where appropriate.

---

# 16. Failure Handling Rules

## Collection Failure

Do not fabricate data.

Record the failure.

Preserve existing run state.

Allow compatible imported or cached demonstration data.

---

## Model Failure

Use limited retries where appropriate.

If semantic analysis still fails:

```text
record failure
preserve already collected/cleaned reviews
do not fabricate findings
```

---

## Invalid Structured Model Output

Validate.

Retry only a limited number of times.

Fail explicitly if output remains invalid.

---

## Insufficient Evidence

Insufficient evidence is a valid analysis result.

Do not force every dataset to produce a large PRD.

---

# 17. UI Priorities

UI priority order:

```text
information architecture
evidence visibility
traceability
readability
workflow clarity
visual polish
animation
```

Do not sacrifice core logic to build decorative animation.

---

# 18. High-Priority UI Features

The most important interview pages/components are:

```text
New Analysis
Findings
Evidence Viewer
Requirements
Version Plan
Test Cases
Traceability
```

The Traceability view is a primary showcase.

---

# 19. Progress Handling

For the interview version:

```text
FastAPI stores run state
React polls status every 1–2 seconds
```

Do not introduce WebSocket/Celery unless a real blocker appears.

Use one FastAPI process with a single worker and an in-process background execution mechanism. Persist each completed stage before starting the next one. `AnalysisRun` must include `current_stage`, `last_successful_stage`, `status`, `warnings`, and `errors`.

Allowed run statuses are:

```text
PENDING
RUNNING
COMPLETED
WARNING
FAILED
```

Cached results must be visibly marked `CACHED RESULT` or `DEMO RESULT` and preserve `source`, `collection_time`, `model_provider`, `model_name`, and `analysis_time`. Never present cached artifacts as a new live run.

---

# 20. Git Rules

Use incremental meaningful commits.

Good examples:

```text
chore: initialize React and FastAPI project
feat: define review analysis domain models
feat: implement review ingestion providers
feat: add review cleaning and deduplication
feat: implement model-driven topic discovery
feat: add evidence-grounded findings
feat: implement evidence validation
feat: generate product requirements
feat: add release planning and PRD generation
feat: generate traceable test cases
feat: implement traceability validator
feat: build analysis dashboard
test: add robustness evaluation datasets
docs: complete project documentation
```

Avoid one giant final commit.

---

# 21. Development Phase Rules

## Phase 1 — Skeleton

Only:

```text
frontend scaffold
backend scaffold
models
health API
frontend/backend connectivity
config
logging
test setup
```

Do not start semantic business logic in this phase.

---

## Phase 2 — Data

Implement:

```text
App Store input
CSV
JSON
cleaning
normalization
deduplication
```

Do not implement PRD yet.

---

## Phase 3 — Semantic Analysis

Implement:

```text
LLM provider
dynamic topic discovery
finding generation
```

Do not collapse this into fixed categories.

---

## Phase 4 — Evidence

Implement:

```text
support validation
conflict handling
confidence/evidence strength
status
```

---

## Phase 5 — Product Output

Implement:

```text
requirements
version planning
PRD
test cases
traceability
```

---

## Phase 6 — UI Completion

Expose the complete pipeline in React.

---

## Phase 7 — Stabilization

Only:

```text
tests
bug fixes
README
sample data
cached results
demo flow
```

Do not add major architecture on the final day.

---

# 22. Definition of Done for a Task

Before reporting a task complete, include:

```text
What changed
Files changed
Tests run
Build result
Known limitations
Remaining work
```

Do not claim success if tests or builds are failing.

---

# 23. Definition of Done for the Project

The project is interview-ready only when this flow works:

```text
App Store URL / CSV / JSON
        ↓
Review normalization
        ↓
Cleaning
        ↓
Runtime LLM topic discovery
        ↓
Evidence-grounded findings
        ↓
Conflict/sufficiency evaluation
        ↓
Requirements
        ↓
Version plan
        ↓
PRD
        ↓
Test cases
        ↓
Deterministic traceability validation
        ↓
React UI
```

And:

```text
backend runs locally
frontend runs locally
frontend production build succeeds
tests pass
.env.example exists
sample/cached results exist
README explains setup and limitations
Git history is meaningful
```

---

# 24. First Instruction When Starting Work

When beginning work in this repository:

1. read `README.md`;
2. read `REQUIREMENTS.md`;
3. read `ARCHITECTURE.md`;
4. read this `AGENTS.md`;
5. inspect current repository state;
6. summarize the requested phase;
7. implement only the requested phase;
8. run tests/build;
9. report results.

Do not silently reinterpret the assignment.

---

# 25. Final Principle

The model is responsible for language understanding.

The codebase is responsible for facts, identifiers, validation, and traceability.

Never confuse the two.
