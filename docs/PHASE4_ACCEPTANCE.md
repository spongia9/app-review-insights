# Phase 4 Acceptance — Evidence Grounding and Finding Validation

## 1. Acceptance decision

**Result: PASS**

All Phase 4 hard gates pass:

- semantic support validation executes through the configured runtime model and typed `EvidenceJudgmentOutput`;
- conflict detection is semantic and does not use rating as stance;
- an unsupported Candidate is retained in the audit, marked `UNSUPPORTED`, and excluded from future Requirement eligibility;
- unknown, hallucinated, duplicate, omitted, out-of-batch, and cross-run Review references are rejected;
- provider/timeout/invalid-structured-output failures preserve Reviews and Phase 3 Candidates and do not fabricate a Finding for a failed Candidate.

This acceptance does not implement or claim Requirement, VersionPlan, PRD, TestCase, or final traceability generation.

## 2. Phase 3 prerequisite gate

`docs/PHASE3_ACCEPTANCE.md` records `Result: PASS` and its final gate states that all Phase 3 core scenarios passed. Phase 4 therefore proceeded. No Phase 3 hard-gate failure was present.

## 3. Scenario matrix

| Test | Input | Expected | Actual | Result |
|---|---|---|---|---|
| Strongly Supported | 5 SUPPORTS judgments | `SUPPORTED`, counts derived from lists | `SUPPORTED`, 5 support, 0 conflict | PASS |
| Weak | 2 SUPPORTS judgments | `WEAK` | `WEAK`, low strength | PASS |
| Conflicted | 3 SUPPORTS + 3 CONFLICTS | Material conflict retained | `CONFLICTED`, 3/3, disjoint evidence | PASS |
| Insufficient | 1 SUPPORTS judgment | `INSUFFICIENT` | `INSUFFICIENT` | PASS |
| Unsupported | 3 IRRELEVANT judgments | Audit retained; no downstream eligibility | `UNSUPPORTED`, audit retained, eligibility false | PASS |
| Invalid Review ID | Candidate references absent current-run ID | Reject before provider | `INVALID_REVIEW_ID`, provider call count 0 | PASS |
| Cross-run Review ID | ID exists only in another stored run | Reject as cross-run | `CROSS_RUN_REFERENCE`, provider call count 0 | PASS |
| Hallucinated model ID | Provider returns `R999999` | Retry, fail, never persist as evidence | Two bounded attempts, `FAILED`, no evidence result or stored hallucinated reference | PASS |
| Exact batch coverage | Missing/out-of-batch/duplicate output ID | Reject or correction retry | Deterministic equality/uniqueness checks pass | PASS |
| Multilingual evidence | English + Chinese Reviews; `zh-CN` output | Original text unchanged; Chinese reasons | Exact Review text equality; Chinese reasons | PASS |
| Provider timeout | Retryable timeout | Finite retries; no fake Finding | Two attempts at test limit 1; Reviews/Candidates retained | PASS |
| Invalid structured output | Invalid JSON/schema boundary | Finite retries; explicit failure | `LLM_INVALID_JSON` / schema failures covered | PASS |
| Provider failure | Retryable provider error | Explicit failure; preserve prior stages | `FAILED`; Phase 2 and Phase 3 retained | PASS |
| Real Workout run | Six major Candidates from official 250-Review run | Real DeepSeek stance validation and grounded IDs | 6/6, 117 unique Reviews, 17 batches, zero hallucinated IDs | PASS |
| Human spot check | Seeded random 5 of 6 real final Findings | Claims broadly match sampled evidence | Five of five broadly supported; one broad AI-use excerpt noted below | PASS |
| Browser regression | JSON -> semantic -> evidence -> viewer -> locale switch | Full UI, final stage text, original evidence, no console error | Real DeepSeek flow passed; 0 errors / 0 warnings | PASS |
| Backend suite | Full Pytest suite | All pass | Recorded after final run below | PASS |
| Frontend build | TypeScript + Vite production build | Pass | Passed | PASS |

## 4. Evidence design verified

### 4.1 Structured stance output

Every model response contains:

```text
analysis_run_id
finding_candidate_id
judgments[]:
  analysis_run_id
  finding_candidate_id
  review_id
  stance
  semantic_relevance
  reason
```

Allowed stance values are `SUPPORTS`, `CONFLICTS`, `NEUTRAL`, and `IRRELEVANT`. Pydantic rejects other values such as `PARTIAL_SUPPORT`. The service requires exactly one judgment for every current batch Review ID.

### 4.2 Conflict discovery

The service always validates all Candidate evidence. It then adds potential counter-evidence from:

1. model-derived Topics whose Review lineage overlaps the Candidate;
2. other consolidated Candidates with the same dynamic Topic or overlapping evidence.

Only these additional Reviews are bounded by `EVIDENCE_CONFLICT_POOL_MAX_REVIEWS`; original Candidate IDs are never dropped. `EVIDENCE_BATCH_SIZE` bounds each runtime request. No keyword taxonomy and no `Finding × all Reviews` scan is used.

The deterministic conflicted fixture proves that high or low rating is not used: the Mock provider supplies semantic stance directly, and code preserves three supporting and three conflicting IDs as disjoint sets with `CONFLICTED` status.

### 4.3 Sufficiency and status

Default thresholds:

```text
minimum relevant supports before WEAK: 2
minimum supports for SUPPORTED: 4
minimum support ratio for SUPPORTED: 0.70
minimum material support/conflict counts: 2 / 2
material conflict ratio: 0.30
semantic relevance threshold: 0.55
```

Decision order is `UNSUPPORTED` -> `INSUFFICIENT` -> `CONFLICTED` -> `SUPPORTED` -> `WEAK`. This makes sparse, contradictory, and irrelevant data valid outcomes rather than pipeline errors.

### 4.4 Confidence and Evidence Strength

Final confidence is calculated by code and bounded to `[0, 1]`:

```text
0.40 * average_support_relevance
+ 0.30 * support_ratio
+ 0.20 * bounded_sample_factor
+ 0.10 * evidence_density
- 0.20 * conflict_ratio
```

The automated suite checks confidence bounds. `HIGH` requires `SUPPORTED`, at least 8 supporting Reviews, and confidence at least 0.80. `MEDIUM` requires an eligible supported/weak/conflicted status, at least 4 directional Reviews, and confidence at least 0.55. Remaining results are `LOW`.

Conclusion confidence is additionally capped by status: `WEAK <= 0.69`, `CONFLICTED <= 0.74`, `INSUFFICIENT <= 0.45`, and `UNSUPPORTED <= 0.20`. This calibration prevents a small unanimous sample from presenting high confidence while its sufficiency status is weak or insufficient.

### 4.5 Audit preservation

Each audit stores Candidate IDs, complete validation pool, all four stance partitions, every judgment and reason, validation batches, metrics, status, confidence, Evidence Strength, uncertainty, actual limitations, provider/model, timestamp, revisions, and errors. Final Finding metadata points back to both Candidate and audit. Pydantic enforces unique/disjoint partitions and support/count equality.

## 5. Real Workout runtime validation

### Runtime provenance

| Field | Actual |
|---|---|
| Run ID | `RUN-355FDD3663F1` |
| Source | `apple_customer_reviews_rss` |
| Storefront | `us` |
| Cleaned Reviews | 250 |
| Provider class | `DeepSeekProvider` |
| Provider | `deepseek` |
| Model | `deepseek-v4-pro` |
| Cached/demo | No |
| Candidates selected | 6 |
| Candidates validated | 6/6 |
| Unique Reviews validated | 117 |
| Evidence batches | 17 |
| Hallucinated Review IDs | 0 |
| Final stage | `FINDING_FINALIZATION` |
| Run status | `WARNING` |

`WARNING` is truthful because the App Store RSS source has documented limitations. There is no Phase 4 hard failure.

### Final Findings

| Candidate | Final status | Support | Conflict | Confidence | Strength |
|---|---:|---:|---:|---:|---:|
| `FC-0001` 免费用户被强制付费 | SUPPORTED | 58 | 0 | 0.9600 | HIGH |
| `FC-0003` 广告无法退出 | SUPPORTED | 9 | 0 | 0.8550 | HIGH |
| `FC-0004` AI生成内容不真实 | SUPPORTED | 5 | 0 | 0.7763 | MEDIUM |
| `FC-0005` 锻炼计划缺乏针对性 | SUPPORTED | 5 | 0 | 0.8020 | MEDIUM |
| `FC-0007` 应用内容过时且重复 | SUPPORTED | 8 | 0 | 0.7733 | MEDIUM |
| `FC-0010` 免费试用期未结束即被扣费 | SUPPORTED | 18 | 0 | 0.8967 | HIGH |

The result demonstrates reclassification rather than trusting Phase 3 Candidate IDs. `FC-0001` began with 63 Candidate Review IDs but retained 58 supports. `FC-0003` began with 22 Candidate IDs, validated a 60-Review Topic pool, and retained only nine supports; the remaining Reviews were neutral or irrelevant to the exact “cannot exit ads” claim. `FC-0007` retained its eight original supports while 52 additional Topic-pool Reviews were correctly excluded from supporting evidence.

No material counter-evidence was found in the bounded Topic pools for these six selected claims. Conflict behavior is therefore demonstrated by the controlled semantic fixture, not fabricated into the real Workout result.

## 6. Human evidence spot check

Selection method: `random.Random(20260814).sample(...)` over the six real final Findings, selecting five. Up to three SUPPORTS and up to three CONFLICTS were requested per Finding. No selected real Finding contained a valid CONFLICTS judgment.

### 6.1 免费试用期未结束即被扣费 — PASS

- `R000110`: “I signed up ... advertised a free trial. I was charged the same day...”
- `R000117`: “says free but charges me on the second day”
- `R000141`: “pay nothing now ... charged $52.99 instantly...”

All three directly support early or immediate charging during an advertised free period.

### 6.2 AI生成内容不真实 — PASS with nuance

- `R000003`: describes “lots of AI use” while expressing disappointment; this is broad corroboration but less specific about realism.
- `R000010`: says the experience is “all AI” and materially worse than the earlier app.
- `R000018`: contrasts real women avatars with “cheesy AI mockups” and “FAKE AI women.”

The Finding is broadly supported, especially by `R000010`, `R000018`, and the other retained evidence. The first excerpt alone would not justify the full claim; this limitation is why multi-review sufficiency is required.

### 6.3 免费用户被强制付费 — PASS

- `R000003`: says the app changed so it can no longer be used for free.
- `R000008`: says years of free use ended and workouts now require payment.
- `R000010`: says it used to be free and now requires payment.

All three directly support the claim.

### 6.4 广告无法退出 — PASS

- `R000002`: says there is no way to exit after a 90-second ad.
- `R000055`: says content remains unavailable after watching a long ad.
- `R000073`: says the interface traps the user in a paid-version popup with no continuation option.

All three support blocked continuation or inability to exit the advertising flow.

### 6.5 锻炼计划缺乏针对性 — PASS

- `R000021`: selecting “avoid knees” still produces squats and lunges.
- `R000213`: selecting “avoid abs” still produces many ab workouts.
- `R000234`: says avoided areas still receive aggravating moves.

All three directly support ineffective personalization.

## 7. Failure safety

Automated service tests cover `LLM_TIMEOUT`, `LLM_PROVIDER_ERROR`, and `LLM_INVALID_JSON`. With a retry limit of one they make exactly two attempts and then persist:

```text
run.status = FAILED
error_code = provider-specific error
Reviews = preserved
SemanticAnalysisResult / FindingCandidates = preserved
no EvidenceValidationResult for the failed first Candidate
```

The invalid-ID provider returns `R999999` twice. Both attempts are rejected by the current-batch allowlist. The final persisted result contains neither a Finding nor an evidence reference to that ID.

## 8. Browser and regression acceptance

Browser run: `RUN-9F8CBF1C06BE`.

```text
Upload sample_data/semantic_smoke_reviews.json
-> 12/12 deterministic ingestion
-> Chinese Analysis Goal and zh-CN output
-> real DeepSeek dynamic Topics and Finding Candidates
-> real DeepSeek Evidence Validation
-> 6/6 final Findings
-> open supporting evidence
-> verify Review ID, rating, version, original Review, stance, and reason
-> switch UI to English
-> generated Chinese analysis remains unchanged
```

The terminal stage displays `证据验证已完成` / `Evidence Validation Completed`, not an active “正在...” label. The language switch changes UI labels but does not translate source Reviews or generated output. Backend health remained connected. Browser console result: 0 errors and 0 warnings.

Screenshot: `output/playwright/phase4-evidence-validation.png` (temporary/ignored test artifact).

Responsive check at `390x844`: `innerWidth=390`, `scrollWidth=390`, no horizontal overflow. The final desktop screenshot was captured at `1440x900`.

The existing App Store, CSV, JSON, cleaning, Analysis Goal, output-language, dynamic Topic, and Finding Candidate tests remain in the full backend suite. The real browser run covers JSON ingestion and Phase 3/4 integration. No Phase 5 API or artifact was created.

## 9. Automated verification

Backend:

```text
80 passed in 3.04s
```

Frontend production build:

```text
TypeScript checks passed
52 modules transformed
Vite production build passed in 177ms
```

Playwright CLI browser acceptance:

```text
real DeepSeek semantic analysis passed
real DeepSeek evidence validation passed
Chinese UI passed
English UI switch passed
source Review text unchanged
evidence viewer passed
390x844 responsive overflow check passed
console: 0 errors, 0 warnings
```

## 10. Known limitations

- Runtime stance judgments are non-deterministic model outputs. Deterministic schema, exact-ID, relevance, status, and audit checks constrain them but cannot make semantic classification infallible.
- Conflict discovery is bounded to Candidate evidence and model-derived Topic lineage. It avoids an expensive all-dataset scan but may miss counter-evidence that Phase 3 assigned to an unrelated Topic; this is disclosed on each Finding.
- The real Workout smoke intentionally validates six major Candidates rather than all 33 to bound API time and cost. The normal UI and API default validate all Candidates; the optional Candidate subset is only a smoke-test control.
- The U.S. RSS feed is undocumented, limited to a recent bounded feed, and externally mutable.
- Evidence validation uses one FastAPI process and in-process background threads. Process termination interrupts the active model call, while persisted Reviews, Candidates, and completed Candidate audits remain available.
- The UI does not restore a prior run after a full page reload; persisted API results remain available. Route/run restoration remains a later UI task.

## 11. Final hard gate

Semantic support validation, conflict handling, unsupported preservation/rejection from downstream eligibility, Review-ID grounding, cross-run isolation, and failure safety all pass. Phase 4 is complete and may proceed to Phase 5 only after a separate user instruction.
