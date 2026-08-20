# App Review Insights — Requirements

## 1. Document Purpose

This document converts the original interview assignment into an executable product and engineering specification.

The project must be completed within one week and submitted as a runnable GitHub project.

The target is not a commercial production system. The target is a complete, credible, locally runnable interview project that demonstrates:

- real review data ingestion;
- deterministic data cleaning and normalization;
- runtime model-driven semantic analysis;
- evidence-grounded product findings;
- product requirement generation;
- multi-version planning and PRD generation;
- requirement-linked test case generation;
- end-to-end traceability;
- robust handling of unknown inputs, conflicting feedback, insufficient evidence, and failures;
- clear UI presentation of the workflow and results.

---

# 2. Product Definition

## 2.1 Product Name

**App Review Insights**

## 2.2 Product Positioning

App Review Insights is an AI-driven product intelligence application that converts App Store user reviews into evidence-grounded product findings, executable requirements, release plans, PRDs, and test cases.

The core business chain is:

```text
Review
  ↓
Finding
  ↓
Requirement
  ↓
TestCase
```

This traceability chain is the central design constraint of the project.

---

# 3. Primary User Flow

The user should be able to:

1. Open the web application.
2. Choose one of the supported data sources:
   - U.S. App Store URL;
   - CSV file;
   - JSON file.
3. Optionally provide an analysis goal or constraint, for example:
   - focus on subscription conversion;
   - focus on workout usability;
   - analyze low-rating reviews;
   - focus on a specific app version;
   - identify issues introduced by a recent release.
4. Start an analysis run.
5. Observe pipeline progress.
6. Inspect:
   - raw reviews;
   - cleaned reviews;
   - topic discovery;
   - findings;
   - evidence;
   - conflicting feedback;
   - requirements;
   - release planning;
   - PRD;
   - test cases;
   - traceability validation.
7. Inspect warnings, failures, revisions, assumptions, and limitations.
8. Review or export generated artifacts where supported.

---

# 4. Mandatory Functional Requirements

## Phase 3 Runtime Semantic Analysis Contract

Phase 3 introduces an Analysis Output Language that is independent from the frontend UI locale. Accepted stored/API values are `FOLLOW_UI`, `zh-CN`, and `en-US`; `FOLLOW_UI` is resolved from the request's UI locale when semantic analysis starts. Original `Review.text` is immutable and is never translated.

Cleaned Reviews are processed in configured batches (`LLM_REVIEW_BATCH_SIZE`, default 25) without sampling. Every batch sends only ID, rating, title, text, version, language, and date. It produces structured, run-scoped `TopicCandidate` and `FindingCandidate` objects. `FindingCandidate` has the fixed Phase 3 disposition `UNVALIDATED_CANDIDATE` and must never be presented as a Phase 4 evidence-validated `Finding`.

Every model response must pass Pydantic schema validation plus deterministic `analysis_run_id`, Review ID, and batch ID allowlist checks. Batch calls may reference only current-batch Reviews. Consolidation may reference only current-run Reviews and source batches, and it must preserve the source Topic/Finding Review-ID lineage. Invalid structured output, timeout, provider failure, or invalid identifiers receive only the configured finite correction retries; exhaustion fails the semantic run without fabricated output.

Cross-batch consolidation must use bounded hierarchical groups rather than one unbounded final request. The default consolidation group size is four source units. Every completed round must persist a run-scoped checkpoint containing the consolidated units and audit artifacts. If consolidation fails after Finding extraction, a retry must reuse the compatible persisted batch results and latest completed consolidation checkpoint; it must not repeat successful Topic discovery or Finding extraction calls.

Provider failures must distinguish output truncation, empty content, malformed JSON, Pydantic schema mismatch, content filtering, capacity failure, timeout, and HTTP/provider errors. Safe diagnostics may include response ID, finish reason, token counts, content character count, JSON line/column, and validation field locations. API keys, full Review text, and raw model responses must not be stored in failure diagnostics. A truncated response must not be retried unchanged.

If a schema-valid consolidation omits source Review lineage, the deterministic validator may repair only by carrying the affected original source Topic/Finding Candidate forward unchanged and recording a revision. It must not attach an omitted Review ID to a different generated claim. Unknown, cross-run, or out-of-group Review IDs remain rejection conditions and cannot be repaired into scope.

Persist transparency fields `total_review_count`, `analyzed_review_count`, `batch_count`, `batch_size`, `sampling_strategy`, `model_provider`, `model_name`, `analysis_goal`, `output_language`, and resolved output language. Persist run-scoped topic draft, finding draft, and consolidation draft audit artifacts at stage boundaries. Phase 3 explicitly excludes final evidence status, Requirements, VersionPlan, PRD, TestCases, and final traceability validation.

## Phase 4 Evidence Grounding Contract

Phase 4 preserves three separate layers:

```text
FindingCandidate (UNVALIDATED_CANDIDATE)
  -> EvidenceValidationAudit
  -> Finding
```

Before any semantic call, deterministic validation must reject a Candidate belonging to another run, a Review ID absent from the current run, an ID owned only by another run, or duplicate Review references. Invalid identifiers never enter semantic validation.

The runtime LLM must return structured `EvidenceJudgment` objects for every Review in each validation batch. Stored/API stance values are fixed English enums:

```text
SUPPORTS
CONFLICTS
NEUTRAL
IRRELEVANT
```

Each judgment contains `analysis_run_id`, `finding_candidate_id`, `review_id`, `stance`, `semantic_relevance`, and a reason in the resolved Analysis Output Language. The returned Review-ID set must equal the batch allowlist exactly. Rating alone cannot determine stance. A `SUPPORTS` or `CONFLICTS` judgment below `EVIDENCE_SEMANTIC_RELEVANCE_THRESHOLD` is deterministically reclassified as `IRRELEVANT` with a revision record.

Conflict discovery must validate all Candidate evidence and may extend the pool with Reviews from overlapping model-derived Topic lineage and same-Topic Candidates. Additional conflict candidates are bounded by `EVIDENCE_CONFLICT_POOL_MAX_REVIEWS`; Candidate evidence itself is never truncated. Reviews are processed in `EVIDENCE_BATCH_SIZE` batches. The implementation must not perform an uncontrolled `Finding × all Reviews` scan.

The default deterministic status rules are:

```text
UNSUPPORTED  support_count == 0
INSUFFICIENT 0 < support_count < EVIDENCE_MIN_RELEVANT_REVIEWS
CONFLICTED   support_count and conflict_count both meet the material minimum,
             and conflict_ratio meets EVIDENCE_CONFLICT_RATIO_THRESHOLD
SUPPORTED    support_count meets EVIDENCE_SUPPORTED_MIN_COUNT,
             support_ratio meets EVIDENCE_SUPPORTED_MIN_RATIO,
             and average support relevance meets the relevance threshold
WEAK         valid support exists but none of the stronger rules pass
```

The code-derived metrics are:

```text
directional_count = support_count + conflict_count
support_ratio = support_count / directional_count
conflict_ratio = conflict_count / directional_count
evidence_density = directional_count / validated_review_count
sample_factor = min(1, directional_count / EVIDENCE_CONFIDENCE_SAMPLE_CAP)

confidence = clamp(
  0.40 * average_support_relevance
  + 0.30 * support_ratio
  + 0.20 * sample_factor
  + 0.10 * evidence_density
  - 0.20 * conflict_ratio,
  0,
  1
)
```

After the formula, deterministic status-specific caps must prevent a sparse or refuted conclusion from displaying strong confidence solely because a few judgments agree. Default caps are `0.69` for `WEAK`, `0.74` for `CONFLICTED`, `0.45` for `INSUFFICIENT`, and `0.20` for `UNSUPPORTED`; all caps are configurable.

Model-provided confidence is never used as final confidence. `HIGH` Evidence Strength requires a `SUPPORTED` Finding plus the configured high sample/confidence thresholds. `MEDIUM` requires an eligible supported/weak/conflicted status, the configured minimum directional sample, and the medium confidence threshold. All other cases are `LOW`.

Uncertainty text must state actual calculated evidence conditions. Finding limitations may include only current-run source limitations, confirmed storefront scope, validation-pool coverage, configured pool bounding, and actual missing metadata. Unsupported Candidates and their judgments remain in the audit, their Finding is marked `UNSUPPORTED`, and they are ineligible for future Requirement generation by default.

Provider timeout, invalid structured output, invalid IDs, and provider failure use the existing finite retry policy. Exhaustion produces `FAILED`, preserves Reviews, Phase 3 Candidates, and completed audit work, and never fabricates a validated Finding for the failed Candidate. Phase 4 explicitly excludes Requirement, VersionPlan, PRD, TestCase, and final traceability generation.

## FR-001 — U.S. App Store URL Input

The system must accept a valid U.S. App Store application URL.

Example:

```text
https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684
```

The example app is a demonstration target only.

The application must not depend on this specific app.

### Acceptance Criteria

- The App ID can be extracted from a valid App Store URL.
- The input is validated.
- Invalid URLs produce a clear error.
- The downstream analysis does not contain hard-coded logic specific to the example app.

---

## FR-002 — Review Data Collection

The system must retrieve real review data for the target app when the configured collection method is available.

The collected data should preserve as much of the following as available:

- review identifier or source identifier;
- title;
- review text;
- rating;
- author;
- version;
- review date;
- storefront;
- source metadata.

### Acceptance Criteria

- Data source and limitations are visible or documented.
- The system does not fabricate reviews when collection fails.
- Collection failure is represented explicitly.
- Collected data can enter the same normalized pipeline as imported data.

---

## FR-003 — CSV Import

The system must support importing review data from a documented CSV format.

### Minimum Supported Fields

The importer should support canonical or mapped versions of:

```text
id
title
text
rating
version
author
date
language
```

Only `text` is strictly required if the importer can generate internal identifiers and safely normalize the remaining optional fields.

### Acceptance Criteria

- A compatible CSV can be uploaded.
- Missing optional fields do not crash the pipeline.
- Malformed rows are reported.
- Imported data is normalized into the common `Review` model.

---

## FR-004 — JSON Import

The system must support importing review data from a documented JSON format.

### Acceptance Criteria

- Compatible JSON arrays or the documented JSON structure can be uploaded.
- Validation errors are shown clearly.
- Imported data is normalized into the common `Review` model.

---

## FR-005 — Analysis Goal

The user must be able to provide an optional natural-language analysis goal.

Examples:

```text
Focus on subscription conversion and low-rating reviews.
```

```text
Analyze usability problems introduced in the latest version.
```

### Acceptance Criteria

- The analysis goal is stored with the analysis run.
- The semantic analysis receives the goal as context.
- Results may adapt to the goal without hard-coded app-specific rules.
- The raw review evidence must remain visible even when analysis is goal-focused.

---

## FR-006 — Review Cleaning

The system must clean and normalize review data using deterministic logic.

The cleaning layer should include:

- empty-text handling;
- duplicate detection;
- normalization of rating;
- normalization of dates;
- normalization of versions;
- whitespace cleanup;
- stable internal review ID assignment;
- preservation of raw source data where practical.

### Acceptance Criteria

The UI or analysis result must be able to report:

```text
raw review count
duplicate count
invalid count
clean review count
```

---

## FR-007 — Dynamic Topic Discovery

The system must dynamically discover topics from the review content.

The core topic discovery logic must not rely only on:

- fixed keyword mappings;
- regular expressions;
- predefined app-specific categories;
- static issue taxonomies.

A model-driven semantic step is mandatory.

### Examples

A fitness app may produce:

```text
Workout timer
Exercise variety
Subscription transparency
Progress tracking
Rest interval
Health integration
```

A music app may instead produce:

```text
Offline playback
Lyrics
Playlist management
Audio quality
Recommendations
Subscription
```

### Acceptance Criteria

- Topics change meaningfully when the input dataset changes.
- The example app is not hard coded.
- Runtime model use can be demonstrated.

---

## FR-008 — Finding Generation

The system must consolidate semantic review signals into structured `Finding` objects.

Each major finding must include at minimum:

```text
finding_id
topic
title
problem
summary
supporting_review_ids
conflicting_review_ids
support_count
conflict_count
confidence
evidence_strength
status
```

### Example

```text
F003

Topic:
Workout Timer

Problem:
Timer state may reset after background/foreground transitions.

Supporting Reviews:
R018
R027
R091

Conflicting Reviews:
R138

Support Count:
3

Confidence:
0.82

Evidence Strength:
MEDIUM

Status:
SUPPORTED
```

---

## FR-009 — Evidence Grounding

Every major finding must preserve evidence.

Evidence must include source Review IDs. Review excerpts may also be stored and displayed, but they do not replace the identifiers required for deterministic traceability.

The system must also preserve:

- supporting evidence count;
- conflicting evidence where material;
- uncertainty;
- limitations.

### Acceptance Criteria

A user must be able to navigate from a finding back to its source reviews.

---

## FR-010 — Conflicting Feedback Detection

The analysis must support conflicting or polarized user feedback.

### Example

```text
8 reviews:
The redesigned UI is harder to use.

5 reviews:
The redesigned UI is clearer than before.
```

The system must not reduce this automatically to:

```text
Users dislike the redesigned UI.
```

It should instead be able to represent the conflict.

### Acceptance Criteria

- Conflicting review IDs are retained.
- Conflict count is visible.
- Conflict can influence finding status and confidence.

---

## FR-011 — Evidence Sufficiency

The system must evaluate whether available evidence is sufficient to support a product conclusion.

Supported statuses should include at least:

```text
SUPPORTED
WEAK
CONFLICTED
INSUFFICIENT
UNSUPPORTED
```

### Expected Behavior

A finding supported by only one ambiguous review should not automatically become a P0 product requirement.

---

## FR-012 — Requirement Generation

Validated findings may be converted into structured product requirements.

Each `Requirement` should include:

```text
requirement_id
title
user_problem
description
finding_ids
review_ids
priority
impact
confidence
acceptance_criteria
target_version
assumption
```

### Acceptance Criteria

- Every non-assumption requirement must trace to at least one finding.
- Its source finding must trace to source reviews.
- Unsupported findings must not silently become requirements.

---

## FR-013 — Release / Version Planning

The system must group requirements into one or more planned releases when appropriate.

Example:

```text
V1.1 — Reliability
V1.2 — Subscription UX
V1.3 — Workout Experience
```

### Acceptance Criteria

- Planning is based on generated requirements.
- Priority, impact, scope, and evidence may influence release grouping.
- Large scope may be split across multiple versions.

---

## FR-014 — PRD Generation

The system must produce a product requirements document based on evidence-grounded findings and requirements.

The PRD should include, where relevant:

- product goal;
- context;
- user problems;
- findings;
- requirements;
- priority;
- release/version plan;
- acceptance criteria;
- evidence references;
- assumptions;
- limitations.

### Acceptance Criteria

The PRD must not contain unsupported claims presented as facts.

---

## FR-015 — Test Case Generation

The system must generate structured test cases based on the product requirements.

Each `TestCase` should include:

```text
test_case_id
requirement_id
source_review_ids
title
preconditions
steps
expected_result
test_type
priority
```

### Acceptance Criteria

- Every test case references a valid requirement.
- The requirement can be traced to source reviews.
- Test cases test whether the requirement addresses the associated user problem.

---

## FR-016 — Traceability Validation

The system must validate the chain:

```text
Review
→ Finding
→ Requirement
→ TestCase
```

### Validation Rules

At minimum:

1. every `supporting_review_id` must exist;
2. every `conflicting_review_id` must exist;
3. every non-assumption requirement must reference a valid finding;
4. every requirement source review must exist;
5. every test case must reference a valid requirement;
6. every source review referenced by a test case must exist;
7. unsupported conclusions must be rejected, revised, or labeled.

### Output

The system should calculate useful coverage information such as:

```text
Finding evidence coverage
Requirement traceability coverage
Test case traceability coverage
Unsupported item count
Weak evidence count
Conflicted finding count
```

---

## FR-017 — Pipeline Progress

The UI must expose analysis execution progress.

Recommended stages:

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

### Acceptance Criteria

The UI can represent:

```text
PENDING
RUNNING
COMPLETED
WARNING
FAILED
```

---

## FR-018 — Intermediate Results

The UI must expose intermediate artifacts where practical.

At minimum:

- raw reviews;
- cleaned reviews;
- topic results;
- findings;
- requirements;
- test cases;
- validation output.

---

## FR-019 — Failure Handling

The application must handle:

- App Store collection failure;
- invalid CSV;
- invalid JSON;
- empty dataset;
- duplicate-heavy dataset;
- model API failure;
- model timeout;
- invalid model structured output;
- unsupported model-generated review IDs;
- insufficient evidence.

### Acceptance Criteria

The application must not fabricate success.

Previously completed deterministic results should remain available where practical.

---

## FR-020 — Cached / Sample Results

The repository should include sample data and/or cached example results so reviewers can inspect the project when external network or model access is unavailable.

Cached results must be clearly labeled.

Cached results must not replace the application's ability to process unseen inputs when the required environment is available.

---

## FR-021 — Run-Scoped Persistence

Every persisted domain object must include `analysis_run_id`:

```text
Review
Finding
Requirement
TestCase
VersionPlan
PRDArtifact
ValidationResult
```

References across different analysis runs are forbidden. Every Review ID lookup and every downstream traceability check must be evaluated against the Review set belonging to the current `analysis_run_id`, not against a global ID set.

### Acceptance Criteria

- Cross-run Review, Finding, Requirement, TestCase, VersionPlan, PRD, or validation references are rejected.
- A locally valid identifier from another run is treated as an invalid reference.
- Validation errors identify both the referencing object and the current run.

---

## FR-022 — U.S. Storefront Provenance

The App Store provider must explicitly collect from the U.S. storefront.

Every collection result must preserve:

```text
source
storefront
collection_time
source_limitations
```

If the provider cannot confirm that the returned reviews came from the U.S. storefront, the result must not be labeled as a compliant live App Store collection. It may be retained only with a warning and explicit provenance limitation.

### Acceptance Criteria

- The requested storefront is `us`.
- The effective storefront and collection time are visible in run metadata.
- Pagination, availability, truncation, rate-limit, and provider limitations are recorded where applicable.
- A China storefront page used only to locate the app must not cause China storefront reviews to be presented as U.S. reviews.

---

## FR-023 — CSV / JSON Contract and Upload Safety

All imported rows must normalize into the common `Review` model.

### Canonical Fields

| Canonical field | Accepted aliases | Required | Behavior |
|---|---|---:|---|
| `id` | `review_id`, `source_review_id` | No | Used as source ID when present; an internal stable ID is always assigned. |
| `text` | `review`, `review_text`, `content`, `body`, `comment` | Yes | Must contain non-whitespace text. |
| `title` | `review_title` | No | Preserved when present. |
| `rating` | `score`, `stars`, `star_rating` | No | Normalized to the supported rating range or reported invalid. |
| `version` | `app_version`, `review_version` | No | Normalized to text. |
| `author` | `user`, `username`, `reviewer` | No | Preserved when present. |
| `date` | `created_at`, `review_date` | No | Normalized to `created_at` when parseable. |
| `language` | `lang`, `locale` | No | Preserved as supplied; detection may enrich but must not replace raw data. |
| `app_id` | `application_id` | No | Preserved when present. |
| `storefront` | `country`, `country_code`, `store` | No | Import provenance only; it does not prove live U.S. collection. |

Canonical field names take precedence over aliases. Ambiguous duplicate mappings are validation errors. Unknown fields may be preserved in `raw_data` and must not alter downstream source-independent behavior.

### CSV Contract

- The file must contain a header row and use UTF-8 or UTF-8 with BOM.
- One data row represents one review.
- The default delimiter is a comma.
- `text` or one accepted text alias must be present.

### JSON Contract

The file must be UTF-8 JSON in one of these forms:

```json
[
  {"id": "source-1", "text": "Review text", "rating": 4}
]
```

or:

```json
{
  "reviews": [
    {"id": "source-1", "text": "Review text", "rating": 4}
  ]
}
```

### Invalid Input Behavior

- A row with missing/blank text or an invalid typed field is rejected and reported with its row/index and reason.
- Valid rows in a partially invalid file may continue, with rejected-row counts and warnings preserved.
- Malformed CSV/JSON, an unsupported top-level JSON shape, or a file with zero valid reviews fails acquisition explicitly.
- The importer must never invent content for a rejected or missing review.

### Upload Limits

For the one-week version, the default limits are:

```text
maximum file size: 10 MiB
maximum parsed records: 10,000
```

Limits may be configurable downward or upward through documented environment settings. The API must enforce the byte limit before unbounded parsing and enforce the record limit during parsing. An over-limit upload is rejected with a clear error; it must not be silently truncated.

### Phase 2 Deterministic Processing Contract

All providers expose the same provider boundary and return run-scoped `List[Review]` after the shared cleaner. App Store collection uses the `us` customer-review RSS JSON feed rather than visible-page HTML. CSV accepts UTF-8/UTF-8 BOM; JSON accepts UTF-8. Other encodings and uncontrolled JSON wrappers are rejected explicitly.

Cleaning normalizes whitespace and optional fields without changing review meaning, validates rating/date values, preserves raw source records where practical, assigns sequential `R000001`-style IDs within the current `analysis_run_id`, and reports structured statistics. Deduplication uses `(source, source_review_id)` when present; otherwise it uses a deterministic normalized title/text/rating fingerprint.

Phase 2 persists the resulting `AnalysisRun`, provider provenance, statistics, rejected-row audit, and cleaned Reviews in SQLite. It stops at `CLEANING_AND_NORMALIZATION` and must not report future semantic stages as completed.

---

## FR-024 — Mandatory Semantic Evidence Validation

Every major Finding must pass both:

```text
A. deterministic ID and run-scope validation
B. semantic support validation
```

The existence of a Review ID proves only referential validity. It does not prove that the Review supports the Finding claim.

Semantic validation must classify cited evidence as supporting, conflicting, ambiguous, or irrelevant (equivalent names are acceptable), and the final Finding evidence status must be derived from validated evidence rather than from an unverified model confidence value.

---

## FR-025 — Finding Evidence Status

The following statuses have fixed semantics:

| Status | Meaning |
|---|---|
| `SUPPORTED` | Valid in-scope evidence semantically supports the claim, material conflicts are within the documented threshold, and sufficiency rules pass. |
| `WEAK` | Some valid support exists, but volume, clarity, representativeness, or confidence is below the supported threshold. |
| `CONFLICTED` | Material valid evidence supports opposing conclusions or user experiences; both sides must remain visible. |
| `INSUFFICIENT` | Available relevant evidence is too sparse or ambiguous to justify a product conclusion. |
| `UNSUPPORTED` | Cited evidence is invalid, irrelevant, or does not semantically support the claim. |

Thresholds and evidence-strength heuristics must be deterministic, transparent, tested, and documented. `WEAK`, `CONFLICTED`, and `INSUFFICIENT` are valid analysis outcomes and must not be inflated into strong recommendations.

---

## FR-026 — Generated Artifact Disposition and Evidence Inheritance

Every AI-generated artifact that can enter a final deliverable, including each Requirement, VersionPlan item, PRD section, and TestCase, must receive one validation disposition:

| Disposition | Meaning |
|---|---|
| `ACCEPTED` | Passed schema, scope, grounding, and traceability validation without material change. |
| `REVISED` | Failed initially, was corrected within allowed evidence, and the validated revision is retained with an audit record. |
| `REJECTED` | Cannot be supported or safely corrected; excluded from final artifacts. |
| `ASSUMPTION` | Retained only as an explicit, visibly labeled assumption and never presented as an evidenced fact. |

### Requirement Evidence Inheritance

- A model may choose only valid current-run `finding_ids` and may not freely invent `review_ids`.
- `Requirement.review_ids` must be deterministically derived from the validated `supporting_review_ids` of its referenced Findings.
- If a model proposes a Review subset for focus, it must be a non-empty subset of the allowed evidence set; otherwise the default stored set is the complete derived union.
- The validator must check the configured subset/equality rule and record any correction.

### TestCase Evidence Inheritance

- A TestCase may not create independent Review evidence.
- Its evidence must be inherited through `TestCase -> Requirement -> Finding -> Review`.
- `TestCase.source_review_ids`, when stored, must be a non-empty subset of its Requirement's validated `review_ids`; the default is the inherited Requirement evidence set.
- The validator must reject broken, cross-run, or unsupported chains.

---

## FR-027 — Traceability Coverage and Completion Gates

Coverage is calculated over current-run, non-rejected artifacts:

```text
Finding evidence coverage
= Findings with at least one valid semantically supporting Review / all Findings

Requirement traceability coverage
= non-assumption Requirements with valid Finding and derived Review links
  / all non-assumption Requirements

TestCase traceability coverage
= TestCases with a valid Requirement and inherited Review chain / all TestCases

Overall traceability coverage
= fully traceable Finding, Requirement, and TestCase artifacts
  / all artifacts included in those three denominators
```

An empty denominator must be reported as `N/A`, not as a misleading 100%. Assumptions and rejected artifacts are reported separately and are not used to improve evidence coverage.

### Hard Failure Conditions

- Unknown or cross-run identifier reference.
- Count/list mismatch or overlapping supporting/conflicting evidence after validation.
- Non-assumption Requirement with no valid Finding or derived Review evidence.
- TestCase with no valid Requirement-to-Review chain.
- Unlabeled unsupported conclusion in a final artifact.
- Final PRD contains an unvalidated factual claim or reference.

### Warning Conditions

- A retained `WEAK`, `CONFLICTED`, or `INSUFFICIENT` Finding.
- An explicit `ASSUMPTION`.
- Partial analysis, sampling, provider limitation, or rejected input rows.
- A planned Requirement without adequate TestCase coverage.

A run may complete with `WARNING` when no hard failure remains. It may be `COMPLETED` only when hard failures are zero and all required traceability denominators are 100%.

---

## FR-028 — Structured PRD

The model must not directly produce uncontrolled final Markdown. The required flow is:

```text
Structured PRD Model
  -> schema and evidence validation
  -> deterministic Markdown renderer
```

Every factual PRD section must be derived only from:

```text
validated findings
validated requirements
validated version plan
explicit assumptions
known limitations
```

Assumptions and limitations must be visibly separated from supported facts. Rejected sections must not enter final Markdown. IDs, statistics, counts, and provenance metadata must be injected from validated application data rather than invented in prose.

---

## FR-029 — Analysis Transparency, Audit Artifacts, and Cached Provenance

When the cleaned Review set exceeds the configured model context strategy, the pipeline must use bounded batches followed by consolidation. It must record:

```text
total_review_count
analyzed_review_count
sampling_strategy
batch_count
```

`sampling_strategy` is `none` when all cleaned reviews are analyzed. Any sampling, filtering, or truncation must be displayed as a limitation; the UI must never imply full-dataset analysis when only a subset was processed.

The pipeline must preserve the following run-scoped intermediate audit artifacts where produced:

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

Cached or demonstration results must display `CACHED RESULT` or `DEMO RESULT` and preserve:

```text
source
collection_time
model_provider
model_name
analysis_time
```

They must never be presented as a new live collection or live model run.

---

## FR-030 — Backend Execution and Stage Persistence

The one-week version must use a single FastAPI process with one worker and a simple in-process background execution mechanism. It must not require Redis, Celery, WebSocket, or a distributed task queue.

Every pipeline stage must persist its output and terminal stage state before the next stage begins. `last_successful_stage` advances only after that persistence succeeds. If a network, model, or process failure interrupts a run, already persisted results remain inspectable.

`AnalysisRun` must record:

```text
current_stage
last_successful_stage
status
warnings
errors
```

Allowed statuses are:

```text
PENDING
RUNNING
COMPLETED
WARNING
COMPLETED_WITH_WARNINGS
FAILED
VALIDATION_FAILED
```

`WARNING` remains the terminal value for a standalone stage execution. The unified full pipeline uses `COMPLETED_WITH_WARNINGS` when final deterministic validation has no hard failure but warnings remain, and `VALIDATION_FAILED` when final structural traceability validation fails.

The single-process/single-worker limitation and lack of distributed automatic recovery must be documented as one-week implementation limitations.

---

## FR-031 — Grounded Product Planning Contract

Phase 5 consumes only the current AnalysisRun's validated Findings. The interview implementation admits `SUPPORTED` Findings into formal Requirement generation and conservatively excludes `WEAK`, `CONFLICTED`, `INSUFFICIENT`, and `UNSUPPORTED` Findings. Excluded Findings remain persisted and visible; `UNSUPPORTED` content must never become a formal Requirement.

### Requirement generation and validation

The runtime model may propose Requirement language, referenced current-run Finding IDs, impact, priority, and testable Acceptance Criteria. It must not generate Review IDs. Processing order is mandatory:

```text
structured Requirement draft
-> Finding/run-scope validation
-> semantic claim-boundary decision
-> Acceptance Criteria validation
-> deterministic Review evidence inheritance
-> deterministic priority calibration
-> final disposition
```

`Requirement.review_ids` must equal the stable union of `supporting_review_ids` from all referenced Findings in the current implementation. A partial or untestable draft must be revised within the validated Finding boundary and retain its original draft and reason. An ungrounded draft is `REJECTED` and cannot enter later stages.

Priority uses `P0` through `P3` and stores `recommended_priority`, `final_priority`, and `priority_reason`. Thresholds must be centralized in configuration. `WEAK` evidence may never automatically become `P0`; assumptions are capped at `P3`. A deterministic priority correction produces `REVISED`.

### VersionPlan validation

The runtime model may choose the number and themes of versions. Deterministic validation requires every accepted/revised Requirement to appear exactly once. Unknown, duplicate, omitted, or cross-run Requirement IDs are hard failures unless an omission is explicitly represented outside the formal plan with a validated rationale; the current implementation uses exact coverage.

### Structured PRD and deterministic Markdown

The model returns `StructuredPRDDraft`, never final Markdown. The application validates every Finding, Requirement, VersionPlan, and version-item reference, rejects `UNSUPPORTED` or rejected references, and reconstructs factual sections, counts, provenance, assumptions, and known limitations from validated current-run artifacts. Only then may code render `PRD.md` deterministically. The rendered Markdown and its StructuredPRD source must be persisted together.

### TestCase generation and traceability

The runtime model may propose TestCase behavior but must not generate Review evidence. Every final TestCase must reference an accepted/revised current-run Requirement, contain at least two observable steps and a verifiable expected result, and store the exact inherited `Requirement.review_ids` set. Unknown Requirements, independent Review IDs, cross-run evidence, or incomplete inheritance are hard failures.

The stage sequence is:

```text
REQUIREMENT_GENERATION
VERSION_PLANNING
PRD_GENERATION
TEST_CASE_GENERATION
TRACEABILITY_VALIDATION
```

Each successful stage persists its draft, validation audit, final artifacts available at that point, and `last_successful_stage`. Provider timeout, invalid structured output, or provider failure must preserve validated Findings and already persisted drafts but must not synthesize missing Requirements, PRD, or TestCases.

---

## FR-032 — Unified Pipeline, Final Traceability, and Run Audit

The ordinary user flow must require one `Start Analysis` action after choosing App Store, CSV, or JSON input, Analysis Goal, and Analysis Output Language. Ingestion may complete synchronously, but the same action must automatically queue the remaining persisted stages in order. Separate semantic/evidence/product endpoints may remain for debug and recovery; they must not be required by the normal UI.

`FinalTraceabilityValidator` must deterministically validate every current-run final relationship, VersionPlan assignment, and StructuredPRD reference. It must materialize:

```text
TraceabilityMatrix(review_id, finding_id, requirement_id, version, test_case_id)
ForwardTraceability(Review -> Finding -> Requirement -> TestCase)
ReverseTraceability(TestCase -> Requirement -> Finding -> Review)
```

The matrix may include supporting and conflicting evidence roles and validation dispositions. Rows and indexes are backend artifacts, not frontend-only string assembly. Unknown/cross-run IDs, count/list mismatches, support/conflict overlap, missing Requirement/Finding linkage, invalid inheritance, rejected Requirement references in the formal PRD, and invalid TestCase evidence are hard failures.

The final UI must expose Overview, raw Reviews, cleaning results, Topic drafts/consolidated Topics, Finding Candidates, Evidence Validation, final Findings, Requirement drafts/final Requirements, VersionPlan, StructuredPRD/rendered Markdown, TestCase drafts/final TestCases, Final Traceability, and Run Audit. All new UI is bilingual and responsive. Source Review text remains original.

Run audit events are run-scoped and include at least `STAGE_STARTED`, `STAGE_COMPLETED`, `WARNING`, `ERROR`, `VALIDATION`, `REVISION`, and `REJECTION`. Progress comes from persisted pipeline state; fixed sleeps, frontend self-increment, and a terminal 100% state with active-stage copy are prohibited.

---

# 5. AI Requirements

## AI-001 — Runtime Model Use

At least one core semantic task must be model-driven at runtime.

Recommended model-driven tasks:

- topic discovery;
- issue consolidation;
- finding generation;
- evidence semantic evaluation;
- requirement generation;
- PRD generation;
- test case generation.

Using Codex to write the source code does **not** satisfy this requirement.

---

## AI-002 — Structured Model Output

Model outputs used by application logic should be structured and validated.

Prefer typed/structured objects rather than parsing free-form prose.

---

## AI-003 — Prompt Documentation

The repository must document:

- model provider;
- model name/configuration;
- core prompts or prompt definitions;
- retry/failure policy;
- structured output strategy;
- hallucination mitigation;
- evidence grounding strategy.

---

## AI-004 — Model / Rule Separation

The system must clearly distinguish:

### Deterministic outputs

Examples:

```text
review count
rating distribution
duplicate count
review ID existence
traceability validation
```

### Model-generated outputs

Examples:

```text
semantic topic
finding summary
user problem abstraction
requirement draft
PRD draft
test case draft
```

---

# 6. Core Domain Models

## 6.1 Review

Recommended fields:

```text
id
analysis_run_id
source
source_review_id
app_id
author
rating
title
text
version
language
created_at
storefront
raw_data
```

---

## 6.2 Finding

Recommended fields:

```text
id
analysis_run_id
topic
title
problem
summary
supporting_review_ids
conflicting_review_ids
support_count
conflict_count
confidence
evidence_strength
status
uncertainty
limitations
```

---

## 6.3 Requirement

Recommended fields:

```text
id
analysis_run_id
title
user_problem
description
finding_ids
review_ids
priority
impact
confidence
acceptance_criteria
target_version
assumption
disposition
```

---

## 6.4 TestCase

Recommended fields:

```text
id
analysis_run_id
requirement_id
source_review_ids
title
preconditions
steps
expected_result
test_type
priority
disposition
```

---

## 6.5 AnalysisRun

Recommended fields:

```text
id
source_type
app_id
analysis_goal
filters
model_provider
model_name
status
current_stage
last_successful_stage
progress
started_at
finished_at
warnings
errors
revisions
total_review_count
analyzed_review_count
sampling_strategy
batch_count
```

`AnalysisRun.status` must be one of:

```text
PENDING
RUNNING
COMPLETED
WARNING
FAILED
```

Every pipeline stage must persist its terminal stage state and intermediate artifacts before the next stage starts.

---

## 6.6 Additional Persisted Models

`VersionPlan`, `PRDArtifact`, and `ValidationResult` must each contain:

```text
id
analysis_run_id
```

`PRDArtifact` must distinguish the validated structured source from deterministic rendered Markdown. `ValidationResult` must retain target type/ID, disposition, errors, warnings, and revision history. Intermediate audit artifacts must also be associated with the current run.

---

# 7. UI Requirements

## UI-001 — New Analysis

Must provide:

- App Store URL input;
- CSV upload;
- JSON upload;
- analysis goal;
- optional filters;
- Start Analysis button.

---

## UI-002 — Overview

Recommended metrics:

```text
Raw Reviews
Clean Reviews
Average Rating
Versions
Languages
Topics
Findings
Requirements
Test Cases
```

---

## UI-003 — Reviews

Should support viewing:

- source review text;
- rating;
- version;
- date;
- language;
- cleaning status.

---

## UI-004 — Topics

Should display dynamic topic results and useful distribution information.

---

## UI-005 — Findings

This is a high-priority interview page.

Each finding card/table row should expose:

```text
topic
problem
support count
conflict count
confidence
evidence strength
status
```

Users should be able to inspect the actual supporting and conflicting reviews.

---

## UI-006 — Requirements

Must display generated product requirements and their evidence linkage.

---

## UI-007 — Version Plan

Must display release grouping and requirement assignment.

---

## UI-008 — PRD

Must display the generated PRD in a readable format.

---

## UI-009 — Test Cases

Must display:

- linked requirement;
- source reviews;
- steps;
- expected result;
- type;
- priority.

---

## UI-010 — Traceability

This is a high-priority interview page.

Recommended table:

| Review | Finding | Requirement | Version | Test Case |
|---|---|---|---|---|

Recommended summary metrics:

```text
Traceability Coverage
Unsupported Findings
Weak Evidence
Conflicted Findings
Unlinked Requirements
Unlinked Test Cases
```

---

## UI-011 — Frontend Internationalization

The frontend UI must support `zh-CN` and `en-US`. The default UI locale is `zh-CN`, and an explicit user selection must persist across page refreshes.

UI locale is independent from the future analysis output language. Changing the interface language must not translate source Reviews, alter generated analysis content, or change any stored/API domain value.

Domain enums remain stable English values at the storage and API layers. Frontend translation resources provide display-only labels, including:

| Stable value | `zh-CN` display label |
|---|---|
| `SUPPORTED` | 证据充分 |
| `WEAK` | 证据较弱 |
| `CONFLICTED` | 存在冲突 |
| `INSUFFICIENT` | 证据不足 |
| `UNSUPPORTED` | 缺乏支持 |
| `ACCEPTED` | 已接受 |
| `REVISED` | 已修订 |
| `REJECTED` | 已拒绝 |
| `ASSUMPTION` | 假设项 |

Canonical Chinese UI terminology includes `用户评论`, `主题`, `洞察发现`, `证据`, `支持证据`, `冲突证据`, `产品需求`, `版本规划`, `PRD`, `测试用例`, `可追溯性`, `证据强度`, `置信度`, `分析目标`, and `分析任务`.

---

# 8. Non-Functional Requirements

## NFR-001 — Local Run

The project must run locally with documented commands.

---

## NFR-002 — Clear Configuration

Secrets must be provided via environment configuration.

Provide:

```text
.env.example
```

Never commit real API keys.

---

## NFR-003 — Maintainable Code

The code should have clear separation between:

```text
API
domain models
data providers
cleaning
LLM
pipeline
validation
UI
```

---

## NFR-004 — Tests

At minimum, backend tests should cover:

- URL parsing;
- CSV import;
- JSON import;
- duplicate removal;
- normalization;
- invalid review ID rejection;
- traceability validation;
- insufficient evidence behavior where deterministic;
- pipeline failure handling where practical.

---

## NFR-005 — Frontend Build

The frontend must pass its production build before final submission.

---

## NFR-006 — Complete Git History

Use meaningful incremental commits.

Avoid one giant final commit.

---

# 9. Required Robustness Scenarios

The project must be manually or automatically tested against at least:

## Scenario A — Normal English Reviews

Expected:

```text
normal pipeline completion
```

## Scenario B — Mixed Chinese and English

Expected:

```text
pipeline remains usable
```

## Scenario C — Duplicate Reviews

Expected:

```text
duplicates removed or clearly identified
```

## Scenario D — Conflicting Reviews

Expected:

```text
CONFLICTED or equivalent representation
```

## Scenario E — Only a Few Reviews

Expected:

```text
INSUFFICIENT or WEAK evidence
```

## Scenario F — Invalid Model Review ID

Expected:

```text
validator rejects the unsupported reference
```

## Scenario G — Model Failure

Expected:

```text
clear failure state
no fabricated semantic result
preserve completed intermediate data
```

## Scenario H — Collection Failure

Expected:

```text
clear error
allow CSV/JSON or cached demonstration path
```

## Scenario I — Unseen App / Dataset

Expected:

```text
dynamic topics
no example-app hard coding
```

---

# 10. Explicitly Out of Scope for the One-Week Version

Do not implement unless all mandatory requirements are already stable:

- authentication;
- user accounts;
- role-based access control;
- billing;
- Redis;
- Celery;
- Kafka;
- RabbitMQ;
- Kubernetes;
- microservices;
- vector database;
- RAG;
- LangGraph;
- CrewAI;
- AutoGen;
- mandatory multi-agent architecture;
- large-scale production deployment;
- mobile applications;
- commercial analytics platform features.

---

# 11. MVP Completion Definition

The project is considered interview-ready when the following path works end-to-end:

```text
App Store URL / CSV / JSON
        ↓
Normalized Reviews
        ↓
Cleaning / Deduplication
        ↓
Runtime LLM Dynamic Topic Discovery
        ↓
Evidence-Grounded Findings
        ↓
Conflict / Sufficiency Evaluation
        ↓
Traceable Requirements
        ↓
Version Plan
        ↓
PRD
        ↓
Traceable Test Cases
        ↓
Deterministic Traceability Validation
        ↓
React UI Presentation
```

And:

- the app runs locally;
- a new compatible dataset can be analyzed;
- no example-app-specific taxonomy is required;
- source evidence is inspectable;
- model failures are visible;
- sample/cached results are provided;
- README explains the architecture, AI use, evidence strategy, limitations, and run instructions.
