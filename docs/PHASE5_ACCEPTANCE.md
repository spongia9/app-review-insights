# Phase 5 Acceptance — Grounded Product Planning

Date: 2026-08-20
Result: **PASS**

## Scope and hard-gate prerequisites

Phase 3 and Phase 4 were both `PASS` before Phase 5 started. Phase 5 implemented only Requirement generation, Version Planning, Structured PRD generation and deterministic rendering, TestCase generation, artifact validation, and the underlying deterministic traceability chain. It did not add Phase 6's final Dashboard/traceability visualization.

The Phase 5 hard gates all passed:

- Requirement grounding;
- `UNSUPPORTED` Finding blocking;
- Requirement and TestCase evidence inheritance;
- PRD grounding;
- TestCase-to-Requirement linkage;
- cross-run isolation;
- provider/structured-output failure safety.

## Acceptance matrix

| Test | Expected | Actual | Result | Evidence |
|---|---|---|---|---|
| Supported Finding to Requirement | A current-run `SUPPORTED` Finding can produce a structured, testable Requirement. | Two supported fixture Findings produced final Requirements with preserved drafts and validation decisions. | PASS | `test_supported_findings_generate_grounded_complete_product_plan` |
| Unsupported blocking | `UNSUPPORTED` may not enter formal Requirements. | `F-UNSUPPORTED` remained upstream and was absent from all Requirement references. | PASS | `test_unsupported_and_weak_findings_are_blocked_from_requirements`; real Workout result reported zero unsupported formal Requirements. |
| Weak evidence behavior | `WEAK` may not automatically become `P0`. | Deterministic recommendation capped the weak fixture at `P2`; the conservative admission rule excluded it from formal generation. | PASS | `test_weak_finding_cannot_be_recommended_p0` |
| Requirement grounding/revision | Partial claims are revised; ungrounded claims are rejected and audited. | A `PARTIAL` semantic decision produced a `REVISED` final artifact while retaining the original draft. `UNGROUNDED` produced no final Requirement and persisted `REJECTED` validation records. | PASS | `test_partial_requirement_claim_is_revised_and_original_draft_is_preserved`; `test_ungrounded_requirement_is_rejected_and_audited` |
| Requirement evidence inheritance | Model cannot create Requirement Review IDs; stored evidence is derived from Findings. | Every Requirement stored the exact stable union of referenced Findings' supporting Review IDs. | PASS | `test_supported_findings_generate_grounded_complete_product_plan` |
| Invalid/cross-run Finding evidence | Unknown and cross-run IDs fail before product generation. | `R999999` produced `INVALID_REVIEW_ID`; a Review owned by another run produced `CROSS_RUN_REFERENCE`; provider was not called. | PASS | `test_invalid_and_cross_run_finding_evidence_are_rejected` |
| Priority validation | Final priority follows configured evidence/impact thresholds. | Mock proposals of `P0` with six supports were deterministically revised to `P2`; metadata records the adjustment and reason. | PASS | `test_requirement_priority_is_deterministically_revised` |
| Version Planning | Every accepted/revised Requirement is assigned exactly once. | Exact coverage passed; omission produced `INCOMPLETE_VERSION_PLAN`. | PASS | `test_version_plan_rejects_omitted_requirement`; complete-plan test |
| Structured PRD schema | Model returns structured data, not final Markdown. | `StructuredPRDDraftOutput` parsed through Pydantic; final factual sections were reconstructed from validated artifacts. | PASS | `test_structured_prd_schema_and_unsupported_reference_rejection` |
| PRD unsupported-reference rejection | PRD may not cite an `UNSUPPORTED` Finding as a formal fact. | Injected `F-UNSUPPORTED` produced `PRD_UNSUPPORTED_REFERENCE`. | PASS | same test; deterministic renderer unit path in complete-plan test |
| PRD artifact download | Validated PRD is downloadable as UTF-8 `PRD.md`. | Endpoint returned `Content-Disposition: attachment; filename="PRD.md"`; browser download preserved Chinese content. | PASS | product-plan API test; Playwright download to `.playwright-cli/PRD.md` |
| TestCase Requirement linkage | Every TestCase references a current-run accepted/revised Requirement. | Unknown `REQ-UNKNOWN` was rejected; validated Requirements and PRD remained, no fake TestCases were created. | PASS | `test_test_case_with_unknown_requirement_is_rejected_without_fake_tests` |
| TestCase evidence inheritance | TestCase evidence is inherited from its Requirement. | Every final TestCase stored the exact Requirement Review set; injected `R999999` caused a traceability hard failure. | PASS | `test_test_case_linkage_and_evidence_inheritance`; `test_invalid_test_case_evidence_is_a_traceability_hard_failure` |
| Traceability coverage | Applicable Finding, Requirement, and TestCase coverage is 100% with zero hard failures. | Mock, real Workout, and browser Music runs all reported overall coverage `1.00`. | PASS | complete-plan test; real smoke; Playwright UI summary |
| Analysis Output Language | Every Phase 5 prompt receives the resolved output language; UI locale remains independent. | All mock prompt payloads carried `zh-CN`; real English UI continued showing Chinese generated Requirements and PRD without modifying Review text. | PASS | `test_output_language_propagates_to_every_product_prompt`; Playwright bilingual check |
| Timeout / malformed output / provider failure | No missing artifact may be fabricated and completed upstream data remains. | Each error exhausted the configured finite retry count, persisted `FAILED`, preserved validated Findings, and left final Requirements/PRD/TestCases empty at the failed boundary. | PASS | parameterized `test_provider_failure_preserves_validated_findings_without_fake_artifacts` |
| API background flow | UI can start, poll, fetch, and download product artifacts. | POST returned 202; polling reached `TRACEABILITY_VALIDATION`; GET returned final artifacts; Markdown endpoint downloaded successfully. | PASS | `test_product_plan_api_starts_polls_and_returns_artifacts`; Playwright flow |

## Real Workout for Women runtime result

Run: `RUN-355FDD3663F1`

| Field | Actual |
|---|---|
| Source | `apple_customer_reviews_rss` |
| Cached/demo | `false` |
| Storefront dataset | 250 previously collected U.S. storefront Reviews |
| Runtime provider | `deepseek` (`DeepSeekProvider`) |
| Runtime model | `deepseek-v4-pro` |
| Output language | `zh-CN` |
| Eligible validated Findings | 6 `SUPPORTED` |
| Final Requirements | 6 |
| VersionPlan items | 2 |
| Final TestCases | 13 |
| Overall traceability | 100% |
| Hallucinated Review IDs | 0 |
| Unsupported formal Requirements | 0 |
| Final run status | `WARNING` only because real source/method limitations remain visible; no hard failure |

The generated UTF-8 artifact was written locally to the ignored path `backend/data/artifacts/RUN-355FDD3663F1/PRD.md` and contained a complete product goal, deterministic background/scope, six user problems, six Finding summaries, six Requirements, two release sections, Acceptance Criteria, evidence counts, assumptions, and actual limitations.

## Human product review — real Workout run

`PARTIAL` means the Requirement is directionally grounded but contains a product-policy or implementation choice beyond the literal user claim; it is acceptable only as a visible `REVISED` artifact, not as a new user fact. No reviewed Requirement was `UNGROUNDED`.

| Source Finding | Requirement | Acceptance Criteria assessment | Evidence | Human result |
|---|---|---|---|---|
| 免费用户被强制付费 | 恢复免费用户对原有免费锻炼内容的访问 | Observable access and paywall behavior; “all previously free content” is a bounded product-policy choice rather than a measured user fact. | 58 inherited Review IDs | PARTIAL / correctly `REVISED` |
| 广告无法退出 | 修复广告无法退出的问题 | Close control appears after playback and returns immediately to the app. | 9 inherited Review IDs | GROUNDED |
| AI生成内容不真实 | 减少或替换疑似AI生成的虚假内容 | Replacement/source disclosure is testable, but the exact replacement policy is a product choice. | 5 inherited Review IDs | PARTIAL / correctly `REVISED` |
| 锻炼计划缺乏针对性 | 根据用户限制个性化锻炼计划 | Knee-limit exclusions and alternative actions are observable and directly address the Finding. | 5 inherited Review IDs | GROUNDED |
| 应用内容过时且重复 | 更新锻炼内容库，减少重复和过时内容 | Non-duplication and update log are testable; update cadence remains a planning choice. | 8 inherited Review IDs | PARTIAL / correctly `REVISED` |

## Human TestCase review — real Workout run

| Requirement | Test | Expected result assessment | Human result |
|---|---|---|---|
| 恢复免费用户对原有免费锻炼内容的访问 | 验证免费用户可访问原有免费锻炼内容 | Directly verifies access without a paywall. | TESTS_REQUIREMENT |
| 恢复免费用户对原有免费锻炼内容的访问 | 验证免费用户访问付费内容时显示升级提示但不阻止原有免费内容 | Separates paid-content messaging from retained free access. | TESTS_REQUIREMENT |
| 修复广告无法退出的问题 | 验证广告播放结束后关闭按钮出现且可点击 | Verifies timing, clickability, and return state. | TESTS_REQUIREMENT |
| 修复广告无法退出的问题 | 验证广告播放中用户可随时退出 | Covers the Requirement description's “allow exit” behavior as an additional functional scenario. | TESTS_REQUIREMENT |
| 减少或替换疑似AI生成的虚假内容 | 验证AI生成内容已被替换为真实素材 | Directly checks the Requirement's replacement outcome. | TESTS_REQUIREMENT |

No reviewed TestCase was `MISMATCH`. The broader real run produced 13 tests and every test inherited the exact Review set of its linked Requirement.

## Playwright end-to-end acceptance

Browser run: `RUN-96DF6DEE2AA3`, using the committed mixed English/Chinese Music App fixture (`24` Reviews) with the analysis goal focused on offline playback, lyrics, collaborative playlists, and recommendations.

The browser completed:

```text
JSON import
-> cleaning (24/24)
-> real DeepSeek semantic analysis
-> 4 dynamic Music topics
-> 4/4 validated Findings
-> 4 Requirements
-> 2 VersionPlan items
-> structured PRD + PRD.md download
-> 15 TestCases
-> 100% overall traceability
```

The four Topics were offline playback, lyric synchronization/display, collaborative playlist editing/synchronization, and repetitive/irrelevant recommendations. No Workout taxonomy appeared. Requirement source-Finding and source-Review disclosures were expanded in the browser and showed the original Review text plus stable internal Review IDs. Switching the UI to English translated UI labels while the `zh-CN` analysis output stayed Chinese. At `390x844`, `document.documentElement.scrollWidth` equaled `window.innerWidth` (`390`) with no horizontal overflow.

Playwright console result: `Errors: 0`, `Warnings: 0` (three informational messages only).

Screenshots:

- `output/playwright/phase5/phase5-product-planning-desktop.png` (`1440x900`)
- `output/playwright/phase5/phase5-product-planning-mobile.png` (`390x844`)

## Automated verification

```text
Backend pytest: 98 passed in 5.07s
Frontend production build: PASS (53 modules; 304.02 kB JS, 24.60 kB CSS)
Playwright: PASS
Real DeepSeek Workout smoke: PASS
```

## Known limitations

- Runtime generation remains dependent on the configured DeepSeek account, quota, model availability, and network access.
- The interview architecture uses one FastAPI process and in-process background threads; a process restart can interrupt the active stage, although every completed stage is persisted.
- The Phase 5 frontend is intentionally a minimal sequential workspace. The final cross-artifact dashboard/graph and broader navigation remain Phase 6 work.
- The conservative policy excludes `CONFLICTED` Findings from formal Requirements rather than attempting a risky automatic assumption. Manual Requirement editing remains deferred.
- Traceability uses exact evidence inheritance in Phase 5. A future focused-subset workflow would require an explicit recorded policy and additional validation.

## Final decision

All Phase 5 hard gates passed. **Phase 5 = PASS.** There is no blocker to starting Phase 6 when explicitly requested.
