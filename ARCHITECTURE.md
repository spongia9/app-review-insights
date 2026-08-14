# App Review Insights — Architecture

## 1. Architecture Goal

This architecture is intentionally optimized for a **one-week interview project**.

The design goal is:

```text
maximum product completeness
+
clear AI architecture
+
strong traceability
+
reasonable engineering quality
÷
limited implementation time
```

The project must look and behave like a real application without introducing unnecessary production infrastructure.

---

# 2. Fixed Technology Stack

## Frontend

```text
React
TypeScript
Vite
Tailwind CSS
Axios or fetch
Recharts OR ECharts
```

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

Use a hosted LLM provider through an internal provider abstraction.

The initial implementation may support one real provider.

Do not over-engineer multi-provider routing during the first week.

## Storage

Use:

```text
SQLite
+
JSON / Markdown artifacts
```

SQLite is sufficient for:

- analysis run metadata;
- normalized reviews;
- findings;
- requirements;
- test cases;
- pipeline state.

JSON / Markdown can be used for:

- cached sample results;
- generated PRD;
- debug artifacts;
- exported analysis data.

---

# 3. High-Level System Architecture

```text
┌───────────────────────────────┐
│         React Frontend        │
│                               │
│ New Analysis                  │
│ Overview                      │
│ Reviews                       │
│ Topics                        │
│ Findings                      │
│ Requirements                  │
│ Version Plan                  │
│ PRD                           │
│ Test Cases                    │
│ Traceability                  │
└──────────────┬────────────────┘
               │ HTTP
               ▼
┌───────────────────────────────┐
│         FastAPI Backend       │
│                               │
│ API Layer                     │
│ Pipeline Orchestrator         │
│ Domain Services               │
│ LLM Provider                  │
│ Validators                    │
│ Repositories                  │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│        SQLite / Artifacts     │
└───────────────────────────────┘
```

---

# 4. Core Domain Flow

The application must preserve this domain chain:

```text
Review
  ↓
Finding
  ↓
Requirement
  ↓
TestCase
```

This is not merely a presentation relationship.

It must exist in structured data.

Example:

```text
R018
R027
R091
  ↓
F003
  ↓
REQ005
  ↓
TC009
TC010
```

---

# 5. Recommended Repository Structure

```text
app-review-insights/

├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── client.ts
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   ├── findings/
│   │   │   ├── reviews/
│   │   │   └── traceability/
│   │   ├── pages/
│   │   │   ├── NewAnalysisPage.tsx
│   │   │   ├── OverviewPage.tsx
│   │   │   ├── ReviewsPage.tsx
│   │   │   ├── TopicsPage.tsx
│   │   │   ├── FindingsPage.tsx
│   │   │   ├── RequirementsPage.tsx
│   │   │   ├── VersionPlanPage.tsx
│   │   │   ├── PrdPage.tsx
│   │   │   ├── TestCasesPage.tsx
│   │   │   └── TraceabilityPage.tsx
│   │   ├── types/
│   │   │   └── index.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── analysis.py
│   │   │   ├── import_data.py
│   │   │   └── health.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   └── database.py
│   │   ├── models/
│   │   │   ├── review.py
│   │   │   ├── finding.py
│   │   │   ├── requirement.py
│   │   │   ├── testcase.py
│   │   │   └── analysis_run.py
│   │   ├── providers/
│   │   │   ├── base.py
│   │   │   ├── app_store.py
│   │   │   ├── csv_provider.py
│   │   │   └── json_provider.py
│   │   ├── services/
│   │   │   ├── cleaner.py
│   │   │   ├── statistics.py
│   │   │   ├── topic_discovery.py
│   │   │   ├── finding_service.py
│   │   │   ├── evidence_service.py
│   │   │   ├── requirement_service.py
│   │   │   ├── version_planner.py
│   │   │   ├── prd_service.py
│   │   │   └── testcase_service.py
│   │   ├── llm/
│   │   │   ├── base.py
│   │   │   ├── provider.py
│   │   │   └── schemas.py
│   │   ├── pipeline/
│   │   │   └── orchestrator.py
│   │   ├── validators/
│   │   │   ├── evidence.py
│   │   │   └── traceability.py
│   │   └── main.py
│   │
│   └── tests/
│
├── prompts/
│   ├── topic_discovery.md
│   ├── finding_consolidation.md
│   ├── evidence_review.md
│   ├── requirement_generation.md
│   ├── version_planning.md
│   ├── prd_generation.md
│   └── testcase_generation.md
│
├── sample_data/
├── cached_results/
├── docs/
│   └── DEVELOPMENT_PLAN.md
│
├── AGENTS.md
├── REQUIREMENTS.md
├── ARCHITECTURE.md
├── .env.example
└── README.md
```

This structure is a recommendation, not an excuse to create unnecessary abstraction.

If a simpler implementation preserves the domain boundaries, simplicity wins.

---

# 6. Provider Architecture

All data input methods should converge into the same domain representation.

```text
               ┌──────────────────┐
App Store ────▶│ AppStoreProvider │
               └────────┬─────────┘
                        │
CSV ───────────▶ CSVProvider
                        │
JSON ──────────▶ JSONProvider
                        │
                        ▼
                  List[Review]
```

Recommended interface:

```python
class ReviewProvider(Protocol):
    async def load_reviews(...) -> list[Review]:
        ...
```

The rest of the pipeline should not care where reviews came from.

## 6.1 Provider Result Contract

Every provider result must include both normalized Reviews and provenance metadata:

```text
source
storefront
collection_time
source_limitations
```

`AppStoreProvider` must request the U.S. storefront explicitly and record the effective storefront. If U.S. provenance cannot be confirmed, the provider result is non-compliant for the formal live App Store path and must carry a visible warning. A storefront value supplied by an imported file is provenance supplied by the importer; it is not proof of live U.S. collection.

All returned Reviews are assigned to the current `analysis_run_id` before persistence. Provider and pipeline queries must always include that scope.

## 6.2 CSV / JSON Boundary Contract

Import is intentionally strict and small:

```text
canonical fields:
id, text, title, rating, version, author, date, language, app_id, storefront

aliases:
id <- review_id | source_review_id
text <- review | review_text | content | body | comment
title <- review_title
rating <- score | stars | star_rating
version <- app_version | review_version
author <- user | username | reviewer
date <- created_at | review_date
language <- lang | locale
app_id <- application_id
storefront <- country | country_code | store
```

`text` is the only required semantic field. CSV must have a header and JSON must be either an array of review objects or `{ "reviews": [...] }`. Canonical names win over aliases; ambiguous mappings are errors. Invalid rows are reported by row/index and may be skipped while valid rows continue. Malformed files, unsupported JSON shapes, or zero valid rows fail acquisition.

The default safety limits are 10 MiB and 10,000 parsed records. Enforce bytes before unbounded parsing and records during parsing. Reject over-limit inputs explicitly; never silently truncate them. All limits may be overridden only through documented configuration.

## 6.3 Phase 2 Provider and Cleaning Flow

```text
AppStoreProvider / CSVProvider / JSONProvider
                    ↓
              ProviderBatch
                    ↓
        shared deterministic cleaner
                    ↓
    List[Review] + CleaningStatistics
                    ↓
        SQLite run-scoped JSON record
```

`AppStoreProvider` parses only U.S. `apps.apple.com` URLs and fetches Apple's public `itunes.apple.com/us/rss/customerreviews/.../json` feed. The storefront is encoded in the request path and persisted as `us`; provider failure never falls back to sample data. RSS page limits, schema stability, availability, and network/rate-limit constraints are recorded as source limitations.

The shared cleaner owns normalization, row validation, internal ID allocation, and deduplication. Providers do not embed source-specific behavior downstream. Deduplication by source identity precedes the normalized title/text/rating fingerprint. SQLite persistence intentionally stores the complete validated Phase 2 result as JSON in a minimal `analysis_runs` table; an ORM and migration framework remain deferred.

---

# 7. Domain Models

## 7.1 Review

```python
class Review(BaseModel):
    id: str
    analysis_run_id: str
    source: str
    source_review_id: str | None
    app_id: str | None
    author: str | None
    rating: float | None
    title: str | None
    text: str
    version: str | None
    language: str | None
    created_at: datetime | None
    storefront: str | None
    raw_data: dict | None
```

Important:

- internal `id` must be stable within an analysis run;
- model-generated code must never invent source review records;
- raw input should remain recoverable where practical.

---

## 7.2 Finding

```python
class Finding(BaseModel):
    id: str
    analysis_run_id: str
    topic: str
    title: str
    problem: str
    summary: str

    supporting_review_ids: list[str]
    conflicting_review_ids: list[str]

    support_count: int
    conflict_count: int

    confidence: float | None
    evidence_strength: str
    status: str

    uncertainty: str | None
    limitations: list[str]
    validation_metadata: FindingValidationMetadata
```

Recommended statuses:

```text
SUPPORTED
WEAK
CONFLICTED
INSUFFICIENT
UNSUPPORTED
```

Phase 4 additionally persists:

```text
EvidenceJudgment
  analysis_run_id
  finding_candidate_id
  review_id
  stance
  semantic_relevance
  reason

EvidenceValidationAudit
  id
  analysis_run_id
  finding_candidate_id
  candidate_review_ids
  validation_review_ids
  supporting_review_ids
  conflicting_review_ids
  neutral_review_ids
  irrelevant_review_ids
  judgments
  validation_batches
  status
  confidence
  evidence_strength
  uncertainty
  limitations
  model_provider
  model_name
  validation_time
  revisions
  errors
```

`FindingValidationMetadata` links the final Finding back to its Candidate and audit and stores deterministic metrics, validated Review/batch counts, validation time, and downstream eligibility. Pydantic validators enforce count/list equality, unique/disjoint support/conflict IDs, and run-scope agreement.

---

## 7.3 Requirement

```python
class Requirement(BaseModel):
    id: str
    analysis_run_id: str
    title: str
    user_problem: str
    description: str

    finding_ids: list[str]
    review_ids: list[str]

    priority: str
    impact: str | None
    confidence: float | None

    acceptance_criteria: list[str]

    target_version: str | None
    assumption: bool = False
    disposition: str
```

---

## 7.4 TestCase

```python
class TestCase(BaseModel):
    id: str
    analysis_run_id: str
    requirement_id: str
    source_review_ids: list[str]

    title: str
    preconditions: list[str]
    steps: list[str]
    expected_result: str

    test_type: str
    priority: str
    disposition: str
```

---

## 7.5 AnalysisRun

```python
class AnalysisRun(BaseModel):
    id: str
    source_type: str
    app_id: str | None
    analysis_goal: str | None

    status: str
    current_stage: str
    last_successful_stage: str | None
    progress: int

    model_provider: str | None
    model_name: str | None

    warnings: list[str]
    errors: list[str]
    revisions: list[str]

    total_review_count: int
    analyzed_review_count: int
    sampling_strategy: str | None
    batch_count: int
```

Run status is constrained to:

```text
PENDING
RUNNING
COMPLETED
WARNING
FAILED
```

## 7.6 Run-Scoped Artifacts

The following persisted models must also contain `id` and `analysis_run_id`:

```text
VersionPlan
PRDArtifact
ValidationResult
AuditArtifact
```

`PRDArtifact` stores a validated structured PRD and separately stores its deterministically rendered Markdown. `ValidationResult` stores the target type/ID, validation disposition, errors, warnings, and revision relationship. `AuditArtifact` stores necessary intermediate stage output.

Minimum structured PRD boundary:

```python
class PRDSection(BaseModel):
    id: str
    analysis_run_id: str
    section_type: str
    title: str
    content: str
    finding_ids: list[str]
    requirement_ids: list[str]
    assumption: bool = False
    disposition: str

class StructuredPRD(BaseModel):
    analysis_run_id: str
    title: str
    product_goal: str
    sections: list[PRDSection]
    version_plan_id: str
    assumptions: list[str]
    limitations: list[str]
```

The exact section taxonomy may remain small, but every factual section must carry sufficient IDs for validation before rendering.

Every database read used for reference validation must be constrained by `analysis_run_id`. Global existence checks are forbidden because an identifier that exists in another run is still invalid for the current run.

---

# 8. Pipeline Architecture

Recommended pipeline:

```text
1. Scope Resolution
        ↓
2. Data Acquisition
        ↓
3. Cleaning & Normalization
        ↓
4. Semantic Topic Discovery
        ↓
5. Finding Consolidation
        ↓
6. Evidence Evaluation
        ↓
7. Requirement Generation
        ↓
8. Version Planning
        ↓
9. PRD Generation
        ↓
10. Test Case Generation
        ↓
11. Traceability Validation
```

---

# 9. Stage Responsibilities

## Stage 1 — Scope Resolution

Input:

```text
analysis_goal
filters
source type
```

Output:

```text
resolved analysis context
```

Do not create app-specific hard-coded categories.

---

## Stage 2 — Data Acquisition

Possible sources:

```text
AppStoreProvider
CSVProvider
JSONProvider
```

Output:

```text
raw List[Review]
```

---

## Stage 3 — Cleaning & Normalization

Deterministic.

Responsibilities:

```text
empty text handling
deduplication
rating normalization
date normalization
version normalization
stable internal IDs
```

Output:

```text
clean List[Review]
cleaning statistics
```

---

## Stage 4 — Semantic Topic Discovery

Model-driven.

Input:

```text
clean reviews
analysis goal
```

Output:

```text
dynamic semantic topics
topic-to-review relationships
```

This stage must not depend solely on a fixed taxonomy.

### Phase 3 implementation boundary

`SemanticAnalysisService` partitions the ordered clean Review list into bounded batches and calls one configured `LLMProvider`. The interview implementation supplies `DeepSeekProvider` through an OpenAI-compatible Chat Completions request with JSON Output. Provider JSON is not trusted as a domain object: it is parsed into Pydantic `TopicDiscoveryOutput`, `FindingCandidateOutput`, or `ConsolidatedAnalysisResult` and then checked against deterministic run/batch allowlists.

```text
List[Review]
  -> create_review_batches
  -> TopicDiscoveryOutput per batch
  -> FindingCandidateOutput per batch
  -> bounded ConsolidatedAnalysisResult groups
  -> persisted consolidation round checkpoints
  -> final ConsolidatedAnalysisResult
```

Only semantic fields needed for the task are serialized to the provider; `raw_data` is excluded. Prompt resources are versionable files under `backend/app/prompts`. Cross-batch consolidation groups at most four source units per request by default, recursively consolidates the resulting units, and persists each completed round as a `ConsolidationCheckpoint`. Every group and the final result must preserve the union of cited Review IDs, exact Finding Review-to-batch mappings, and valid Topic source batches. `FindingCandidate` is stored as `UNVALIDATED_CANDIDATE` and remains separate from the existing final `Finding` domain model.

Analysis Output Language accepts `FOLLOW_UI`, `zh-CN`, or `en-US` and is resolved once when analysis starts; it never mutates the source Review. The service persists each draft stage in the existing run JSON aggregate and updates `current_stage`, `last_successful_stage`, progress, transparency counts, revisions, and failures. A compatible failed run resumes from `FINDING_EXTRACTION` or the latest completed consolidation round. Provider diagnostics distinguish truncation, empty content, malformed JSON, schema mismatch, content filtering, capacity errors, timeouts, and HTTP failures without storing secrets or raw content. Finite correction retries cover only errors that can change on retry; an unchanged truncated request is not repeated. For an otherwise in-scope response that drops lineage, deterministic repair carries the affected original candidate forward rather than attaching its Review IDs to another generated claim; unknown or cross-run IDs are still rejected. Phase 4 alone owns semantic support/conflict/sufficiency validation and final Finding statuses.

If the cleaned dataset does not fit the configured context strategy, use bounded batches and a consolidation pass. Persist `total_review_count`, `analyzed_review_count`, `sampling_strategy`, and `batch_count`. Sampling or truncation is a disclosed limitation, never an implicit implementation detail.

---

## Stage 5 — Finding Consolidation

Model-driven.

Input:

```text
reviews
topics
analysis goal
```

Output:

```text
structured Finding candidates
```

Findings must reference source review IDs.

---

## Stage 6 — Evidence Evaluation

Hybrid:

```text
deterministic validation
+
model semantic evaluation
```

Deterministic checks:

```text
review IDs exist
support counts match
conflicting IDs exist
```

Semantic checks must evaluate for every major Finding:

```text
whether cited evidence actually supports the claim
whether feedback is conflicting
whether evidence is weak
```

For every major Finding, both deterministic validation and semantic support validation are mandatory. Semantic validation classifies each cited Review as supporting, conflicting, ambiguous, or irrelevant. A valid Review ID alone cannot establish support.

The final status semantics are:

```text
SUPPORTED    = sufficient valid semantic support with no material unresolved conflict
WEAK         = valid support exists but clarity, volume, or representativeness is weak
CONFLICTED   = material valid evidence supports opposing conclusions
INSUFFICIENT = relevant evidence is too sparse or ambiguous for a conclusion
UNSUPPORTED  = evidence is invalid, irrelevant, or does not support the claim
```

Counts, ratios, and the documented evidence-strength heuristic are calculated by code. Unverified model confidence must not be treated as evidence.

Output:

```text
validated findings
status
confidence/evidence strength
```

### Phase 4 implementation

Phase 4 keeps the existing aggregate SQLite persistence strategy and adds three separate run-scoped layers:

```text
FindingCandidate
  -> EvidenceValidationAudit
  -> Finding
```

`EvidenceValidationService` first validates every Candidate reference against the current run. A Review ID absent from the current run is rejected before an LLM call; when it exists only in another stored run it is reported as a cross-run reference. The service then builds a bounded validation pool from all Candidate Review IDs plus additional Reviews found through overlapping model-derived Topic lineage and same-Topic Finding Candidates. Only the additional pool is capped; Candidate evidence is never truncated.

```text
candidate evidence
  + bounded model-derived Topic pool
  -> create_evidence_batches(EVIDENCE_BATCH_SIZE)
  -> runtime EvidenceJudgmentOutput
  -> exact current-run/current-batch ID validation
  -> deterministic stance partitions and metrics
  -> Finding + EvidenceValidationAudit
```

The provider returns one `EvidenceJudgment` per allowed Review with `SUPPORTS`, `CONFLICTS`, `NEUTRAL`, or `IRRELEVANT`, semantic relevance, and a short reason. It does not return final status or confidence. Low-relevance directional judgments are deterministically moved to `IRRELEVANT` with a revision. Supporting, conflicting, neutral, and irrelevant sets are unique, disjoint, and exactly cover the validated pool.

Code calculates support/conflict ratios, evidence density, average support relevance, a bounded sample factor, confidence, status, and Evidence Strength from centralized configuration. The confidence formula is:

```text
clamp(
  0.40 * average_support_relevance
  + 0.30 * support_ratio
  + 0.20 * sample_factor
  + 0.10 * evidence_density
  - 0.20 * conflict_ratio,
  0,
  1
)
```

The calculated value is then calibrated with a deterministic status cap: `WEAK <= 0.69`, `CONFLICTED <= 0.74`, `INSUFFICIENT <= 0.45`, and `UNSUPPORTED <= 0.20` by default. These values are configuration, not model output. This prevents a tiny but internally consistent evidence set from appearing highly reliable.

Uncertainty is assembled from the actual status/count/ratio outcome. Limitations are derived only from provider provenance, storefront scope, evidence-pool coverage/bounding, and actual missing metadata. `UNSUPPORTED` Candidates remain visible in the audit and their final Finding is not eligible for downstream Requirement generation. Phase 5 remains responsible for any Requirement decision.

The real progress stages are `EVIDENCE_VALIDATION`, `CONFLICT_ANALYSIS`, and `FINDING_FINALIZATION`. Each completed Candidate audit is persisted. A provider or structured-output failure preserves Reviews, Phase 3 Candidates, and any completed audit work; it never creates a Finding for the failed Candidate.

---

## Stage 7 — Requirement Generation

Model-driven draft + deterministic validation.

Input:

```text
validated findings
```

Output:

```text
requirements
```

Rule:

```text
UNSUPPORTED findings cannot silently generate requirements.
```

The model selects only current-run validated `finding_ids`. It does not freely generate Requirement Review evidence. The persisted `Requirement.review_ids` is the deterministic union of valid supporting Review IDs inherited from the referenced Findings. If a focused subset is supported, it must be a non-empty subset of that allowed union and the applied subset/equality rule must be recorded and validated.

---

## Stage 8 — Version Planning

Model-driven recommendation.

Consider:

```text
priority
impact
evidence
scope
dependency
```

Output:

```text
release plan
```

---

## Stage 9 — PRD Generation

Model-driven structured drafting using only validated project artifacts, followed by validation and deterministic rendering.

Input:

```text
findings
requirements
release plan
analysis goal
limitations
```

Output:

```text
validated StructuredPRD
deterministically rendered PRD Markdown
```

The model must not generate uncontrolled final Markdown. New facts are limited to validated Findings, validated Requirements, the validated VersionPlan, explicit assumptions, and known limitations. IDs, counts, statistics, and provenance are injected from application data. Assumptions and limitations are rendered separately from supported facts.

---

## Stage 10 — Test Case Generation

Model-driven draft + deterministic linkage validation.

Input:

```text
requirements
inherited requirement evidence
```

Output:

```text
TestCase[]
```

The model may not create independent Review evidence. A TestCase inherits its allowed evidence through `TestCase -> Requirement -> Finding -> Review`. Stored `source_review_ids` default to the Requirement evidence set and, when narrowed, must be a non-empty subset. Broken or cross-run chains are rejected.

---

## Stage 11 — Traceability Validation

Deterministic.

Validate:

```text
Review exists
Finding references valid Reviews
Requirement references valid Findings
TestCase references valid Requirement
all references belong to the current AnalysisRun
Requirement Review evidence is inherited from Findings
TestCase Review evidence is inherited from its Requirement
final PRD facts come from validated artifacts
```

Calculate coverage over current-run, non-rejected artifacts:

```text
Finding evidence coverage
= Findings with valid semantic support / all Findings

Requirement traceability coverage
= non-assumption Requirements with valid Finding and derived Review links
  / all non-assumption Requirements

TestCase traceability coverage
= TestCases with a valid Requirement and inherited Review chain / all TestCases

Overall traceability coverage
= fully traceable artifacts across the three levels / all artifacts in their denominators
```

An empty denominator is `N/A`, not 100%. Unknown/cross-run IDs, broken inheritance, support/count mismatches, overlapping support/conflict sets, unlabeled unsupported conclusions, and unvalidated PRD facts are hard failures. Weak/conflicted/insufficient evidence, explicit assumptions, partial analysis, rejected rows, provider limitations, or incomplete Requirement test coverage are warnings. A run is `COMPLETED` only with zero hard failures and 100% for every applicable required coverage metric; otherwise it is `WARNING` or `FAILED` according to whether hard failures remain.

---

# 10. AI Architecture

## 10.1 Provider Interface

Use a simple provider abstraction.

```python
class LLMProvider(Protocol):

    async def discover_topics(...):
        ...

    async def generate_findings(...):
        ...

    async def evaluate_evidence(...):
        ...

    async def generate_requirements(...):
        ...

    async def generate_version_plan(...):
        ...

    async def generate_prd(...):
        ...

    async def generate_test_cases(...):
        ...
```

For the one-week project, implementing one real provider is enough.

---

# 11. Structured Output

LLM application logic should consume typed structured data.

Bad:

```text
"Here is my analysis..."
```

Preferred:

```json
{
  "findings": [
    {
      "topic": "Workout Timer",
      "problem": "Timer resets after background transition",
      "supporting_review_ids": ["R018", "R027"],
      "conflicting_review_ids": ["R138"]
    }
  ]
}
```

Validate model output against Pydantic schemas before saving.

Every generated artifact that can enter a final deliverable, including each Requirement, VersionPlan item, PRD section, and TestCase, receives one validation disposition:

```text
ACCEPTED   = valid without material correction
REVISED    = corrected within the allowed evidence and retained with an audit trail
REJECTED   = excluded because it cannot be supported or safely corrected
ASSUMPTION = retained only with an explicit visible assumption label
```

Rejected artifacts remain in validation audit output but do not enter final deliverables. Assumptions never count as supported evidence.

---

# 12. Hallucination Control Architecture

The system should not treat the LLM as a database.

Use:

```text
LLM Output
   ↓
Schema Validation
   ↓
ID Validation
   ↓
Evidence Validation
   ↓
Accept / Revise / Reject
```

Example:

```text
Model Finding:
Apple Watch integration requested.

Review IDs:
R010
R999
```

If `R999` does not exist:

```text
validation error
```

The system must not silently accept it.

---

# 13. Evidence Confidence

Do not rely only on an arbitrary LLM confidence value.

Recommended evidence indicators:

```text
support_count
conflict_count
support ratio
conflict ratio
semantic evaluator result
dataset size
```

Then derive:

```text
Evidence Strength:
HIGH
MEDIUM
LOW
```

A simple transparent heuristic is acceptable for the interview project.

Document the heuristic.

---

# 14. API Architecture

Keep the API small.

## Health

```http
GET /api/health
```

---

## Create Analysis

```http
POST /api/analysis
```

Example:

```json
{
  "source_type": "app_store",
  "app_url": "https://apps.apple.com/us/app/...",
  "analysis_goal": "Focus on low-rating subscription issues"
}
```

Response:

```json
{
  "run_id": "RUN-001"
}
```

---

## Analysis Status

```http
GET /api/analysis/{run_id}/status
```

Example:

```json
{
  "status": "RUNNING",
  "stage": "EVIDENCE_EVALUATION",
  "progress": 55
}
```

---

## Analysis Result

Prefer one aggregated endpoint first:

```http
GET /api/analysis/{run_id}
```

If needed, add:

```http
GET /api/analysis/{run_id}/reviews
GET /api/analysis/{run_id}/findings
GET /api/analysis/{run_id}/requirements
GET /api/analysis/{run_id}/testcases
GET /api/analysis/{run_id}/traceability
```

Do not create dozens of micro-endpoints unless necessary.

Phase 4 extends the compact API with:

```http
POST /api/analysis/{analysis_run_id}/evidence
GET  /api/analysis/{analysis_run_id}/findings
```

The POST queues in-process validation and accepts an optional run-scoped Candidate ID subset for smoke testing; the normal UI omits it and validates all Candidates. The existing aggregate run endpoint exposes evidence progress/summary for polling. The Findings endpoint returns final Findings plus their EvidenceValidationAudit records so the UI can display original Reviews, stance, and reason without recomputing semantic meaning in React.

---

## Import

Possible design:

```http
POST /api/import
```

Multipart upload:

```text
CSV or JSON
```

The import result should create or feed an analysis run.

Phase 2 implements the compact contract as:

```http
POST /api/analysis/app-store
POST /api/analysis/import/csv
POST /api/analysis/import/json
GET  /api/analysis/{analysis_run_id}
GET  /api/analysis/{analysis_run_id}/reviews
```

Creation endpoints return the complete ingestion result for the minimal synchronous Phase 2 UI. The two GET endpoints keep run status/statistics and cleaned Review retrieval explicit without fragmenting the API into source-specific result endpoints.

---

# 15. Progress Architecture

Do not introduce Celery or WebSocket for the first-week implementation.

Recommended:

```text
backend stores AnalysisRun state
frontend polls every 1–2 seconds
```

Example state:

```text
RUNNING
stage = FINDING_CONSOLIDATION
progress = 45
```

This is sufficient for the interview UI.

## 15.1 One-Week Execution Strategy

Use one FastAPI process with one worker and a simple in-process background execution mechanism. Do not use Celery, Redis, WebSocket, or a distributed queue.

Required behavior:

```text
POST creates a PENDING AnalysisRun
background execution changes it to RUNNING
each stage persists output and terminal stage state
last_successful_stage advances only after that persistence succeeds
final validation selects COMPLETED, WARNING, or FAILED
```

The local one-worker limitation must be documented. A process restart may interrupt an active model/network call, but already committed stage results remain inspectable. Automatic distributed recovery is outside the one-week scope.

## 15.2 Intermediate Audit Persistence

Persist run-scoped audit artifacts for:

```text
topic draft
finding draft
evidence validation
requirement draft
requirement revision
PRD structured draft
test case draft
validation audit
```

These artifacts support progress UI, debugging, and the accept/revise/reject/assumption audit trail. They are not automatically final product artifacts.

---

# 16. Frontend Architecture

Recommended routes/pages:

```text
/new
/analysis/:runId/overview
/analysis/:runId/reviews
/analysis/:runId/topics
/analysis/:runId/findings
/analysis/:runId/requirements
/analysis/:runId/versions
/analysis/:runId/prd
/analysis/:runId/tests
/analysis/:runId/traceability
```

A single analysis workspace with tabs is also acceptable.

Choose whichever is faster and clearer.

## 16.1 Frontend Localization Boundary

Use `i18next` with `react-i18next` and locale resources under `frontend/src/i18n/`. Supported UI locales are `zh-CN` and `en-US`; `zh-CN` is the default. The user's explicit selection is persisted in browser `localStorage` and restored before the application renders.

`ui_locale` and the future `analysis_output_language` are separate concerns. Phase 1.6 implements only `ui_locale`; later analysis requests may add their own explicit output-language field without deriving it from the interface locale.

Backend/domain enum values and API payloads remain stable English identifiers. Translation occurs only at the React presentation layer through display-label mappings. Locale changes therefore do not mutate domain objects, evidence links, cached artifacts, or traceability validation inputs.

---

# 17. Priority UI Components

## 17.1 Finding Card

Display:

```text
Topic
Problem
Support Count
Conflict Count
Confidence
Evidence Strength
Status
```

Action:

```text
View Evidence
```

---

## 17.2 Evidence Drawer / Modal

Display:

```text
supporting reviews
conflicting reviews
rating
version
date
review text
```

---

## 17.3 Traceability Table

Display:

| Review | Finding | Requirement | Version | Test Case |
|---|---|---|---|---|

This is a primary interview showcase feature.

---

# 18. Persistence

SQLite tables can roughly correspond to:

```text
analysis_runs
reviews
findings
requirements
test_cases
version_plans
prd_artifacts
validation_results
audit_artifacts
```

For a one-week interview project, simple JSON columns are acceptable for nested lists such as:

```text
supporting_review_ids
acceptance_criteria
steps
```

Do not spend excessive time designing a perfect relational schema.

Every table holding a persisted domain or audit object includes `analysis_run_id`, and every reference lookup uses it. SQLite foreign keys and service-level validators should reinforce the same run boundary; neither replaces the other.

---

# 19. Failure Strategy

## Collection Failure

Return:

```text
FAILED or WARNING
```

Keep the application usable.

Offer/import data path.

---

## LLM Failure

Recommended:

```text
retry limited number of times
then stop semantic stage
preserve cleaned reviews
record error
```

Never create fake results.

---

## Invalid Structured Output

Recommended:

```text
validate
retry with correction context
then fail explicitly
```

---

## Insufficient Evidence

Do not fail the entire run.

Return findings with:

```text
WEAK
INSUFFICIENT
```

where appropriate.

---

# 20. Sample / Offline Mode

Include:

```text
sample_data/
cached_results/
```

The UI should clearly mark cached results, for example:

```text
Cached Demonstration Result
```

Do not present cached data as a newly fetched live analysis.

Each cached/demo result must retain:

```text
source
collection_time
model_provider
model_name
analysis_time
```

The UI must display `CACHED RESULT` or `DEMO RESULT`. Loading a cached artifact must not update provenance to look like a new live collection or model execution.

---

# 21. Testing Architecture

## Backend

Use Pytest.

High-priority tests:

```text
URL parser
CSV importer
JSON importer
deduplication
normalization
invalid review reference rejection
requirement finding reference validation
test case requirement validation
traceability coverage
pipeline failure state
```

LLM calls may be mocked for deterministic tests.

---

## Frontend

At minimum:

```text
npm run build
```

If time allows:

```text
basic component tests
critical flow browser test
```

Do not sacrifice mandatory backend correctness for extensive frontend test coverage.

---

# 22. Development Strategy

The architecture should be implemented in phases.

## Phase 1

```text
React scaffold
FastAPI scaffold
Pydantic models
health API
frontend-backend connectivity
tests
```

## Phase 2

```text
providers
App Store
CSV
JSON
cleaning
```

## Phase 3

```text
LLM provider
topic discovery
findings
```

## Phase 4

```text
evidence evaluation
confidence
conflict
validators
```

## Phase 5

```text
requirements
version plan
PRD
test cases
traceability
```

## Phase 6

```text
React analysis dashboard
```

## Phase 7

```text
robustness testing
README
sample data
cached results
bug fixes
```

---

# 23. Architecture Decisions That Must Not Drift

During the one-week project, do not change these unless a real blocking issue is demonstrated:

```text
Frontend = React + TypeScript + Vite
Backend = FastAPI + Python
Core Chain = Review → Finding → Requirement → TestCase
Semantic Analysis = Runtime LLM
Data Sources = App Store + CSV + JSON
Traceability = Mandatory
Agent Framework = Not Required
Primary DB = SQLite
Progress = Polling
Execution = Single process / single worker
PRD = Structured model + validation + deterministic renderer
Scope = analysis_run_id on all persisted domain artifacts
```

Avoid technology churn.

---

# 24. Explicit Non-Architecture Goals

Do not optimize for:

```text
enterprise scalability
multi-region deployment
distributed task queues
multi-tenant architecture
complex RBAC
perfect DDD purity
microservices
Redis
Celery
RAG
LangGraph
multi-agent runtime
vector database
authentication / RBAC
WebSocket
complex production deployment
```

The project should be explainable, runnable, traceable, and complete.

That is the architecture standard for this interview.

The following are deferred until mandatory functionality is stable:

```text
complex charting and visualization
advanced export
manual Requirement editing
advanced filters
multiple LLM providers
ORM or complex migration tooling
large frontend component test suites
```
