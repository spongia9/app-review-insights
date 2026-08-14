# Phase 3 Final Acceptance and Runtime Semantic Analysis Verification

## 1. Acceptance decision

**Result: PASS**

Phase 3 satisfies the runtime semantic-analysis requirements that are in scope:

- the configured runtime provider is called for semantic work;
- topics are discovered from review meaning instead of a fixed taxonomy;
- an unseen music-domain dataset produces music-specific topics;
- the analysis goal is present in every model request and changes topic/candidate ordering on a controlled same-input comparison;
- mixed Chinese/English input is accepted and output language is independently controlled;
- every model-generated Review ID is checked against current-run and current-batch allowlists;
- multi-batch results are consolidated without losing the global Topic/Finding Review-ID unions;
- authentication and timeout failures preserve cleaned Reviews and do not fabricate semantic output.

`FindingCandidate` remains an `UNVALIDATED_CANDIDATE`. The spot check in this report is not Phase 4 Semantic Evidence Validation and does not assign `SUPPORTED`, `WEAK`, `CONFLICTED`, `INSUFFICIENT`, or `UNSUPPORTED`.

## 2. Environment and provenance

| Field | Actual value |
|---|---|
| Runtime provider implementation | `DeepSeekProvider` |
| Stored provider | `deepseek` |
| Model | `deepseek-v4-pro` |
| Endpoint family | DeepSeek OpenAI-compatible `/chat/completions` |
| Structured output | JSON Output + local Pydantic validation |
| Runtime mock used for real scenarios | No |
| Cached semantic result used for real scenarios | No |
| Production hard-coded acceptance topics | No matching strings found in `backend/app/**/*.py` |
| Acceptance date | 2026-08-14 |

The untracked `.env` supplied the API credential. The credential and raw provider response were not printed, stored in this report, or committed.

## 3. Scenario matrix

| Scenario | Input | Expected | Actual | Result |
|---|---|---|---|---|
| Official Workout baseline | 250 U.S. App Store Reviews | 250/250 analyzed with dynamic Topics and Finding Candidates | 250/250, 10 batches, 15 Topics, 33 candidates | PASS |
| Analysis Goal A/B | Identical deterministic 36-Review official-data slice | Goal-specific ordering and candidates | Goal A ranks subscription/free/pay first; Goal B ranks training/design/difficulty/usability first | PASS |
| Unknown domain | 25 synthetic Music App Reviews | Music-specific Topics; no Workout taxonomy | Five exact music-domain themes; no Workout terms | PASS |
| Multilingual input | Same 6 English + 6 Chinese Reviews | Chinese output for `zh-CN`, English output for `en-US`, original text unchanged | Six Chinese Topics and six English Topics; all normalized source text remained exactly unchanged during semantic analysis | PASS |
| Hallucinated Review ID | Mock returns `R999999` | Reject and correction retry; never persist it | `INVALID_REVIEW_ID`, second attempt succeeds, `R999999` absent from persisted JSON | PASS |
| 200+ consolidation | Official 250 Reviews / 10 batches | Merge duplicate Topics and preserve lineage | 58 batch Topics -> 15 global Topics; 10 ad-related batch Topics -> 1 global ad Topic; global ID unions exact | PASS |
| Runtime provider | Real semantic runs | `deepseek` / configured model; not mock/cache | `DeepSeekProvider`, `deepseek-v4-pro`, new `analysis_time` and audit artifacts | PASS |
| Invalid API key | Simulated DeepSeek HTTP 401 | Fail explicitly; keep cleaned data; no fake semantic data | `LLM_AUTHENTICATION_FAILED`, `FAILED`, Reviews retained, semantic result absent | PASS |
| Provider timeout | Mock timeout through configured retry boundary | Finite retry, explicit failure, no fake data | Three total attempts with retry limit 2; `FAILED`, Reviews retained, semantic result absent | PASS |
| Human evidence spot check | Five deterministic random candidates | Claims appear broadly supported by cited excerpts | Five of five have direct surface support | PASS |
| Backend suite | Full Pytest suite | All pass | 56 passed | PASS |
| Frontend build | Production TypeScript/Vite build | Build succeeds | Passed | PASS |
| Browser | JSON -> cleaning -> goal/language -> semantic analysis -> evidence viewer | Complete flow, bilingual UI, no console errors | Passed with real DeepSeek Music run; 0 errors / 0 warnings | PASS |

## 4. Official Workout App baseline

### Input

- Run ID: `RUN-355FDD3663F1`
- App ID: `839285684`
- Source: `apple_customer_reviews_rss`
- Storefront: `us`
- Collection time: `2026-08-14T01:08:24.686554+00:00`
- Cleaned Reviews: 250
- Sampling: `NONE`

The source is Apple's storefront-specific public customer-review RSS feed. The run is `WARNING`, rather than `FAILED`, because the feed is undocumented, limited to five recent pages, and externally mutable. This warning is unrelated to semantic-analysis completion.

### Runtime result

| Field | Value |
|---|---|
| `status` | `WARNING` |
| `progress` | 100 |
| `total_review_count` | 250 |
| `analyzed_review_count` | 250 |
| `batch_count` | 10 |
| `batch_size` | 25 |
| `sampling_strategy` | `NONE` |
| `model_provider` | `deepseek` |
| `model_name` | `deepseek-v4-pro` |
| `output_language` | `zh-CN` |
| `analysis_time` | `2026-08-14T02:08:29.720677+00:00` |
| Dynamic Topics | 15 |
| Finding Candidates | 33 |

Examples of dynamically generated Topics include `订阅与付费问题`, `广告体验差`, `锻炼效果与针对性`, `应用质量下降`, `客户支持与账户管理`, `AI生成内容与设计`, `设备集成与数据同步`, `个性化与定制`, and `内容与多样性`.

Examples of generated candidates include `免费用户被强制付费`, `订阅取消困难`, `广告无法退出`, `锻炼计划缺乏针对性`, `应用内容过时且重复`, and `无法连接Apple Watch自动同步数据`.

## 5. Analysis Goal comparison

### Controlled input

Both accepted runs use the exact same ordered 36-Review subset from the official U.S. snapshot. It is deliberately balanced between payment/subscription evidence and workout/content/usability evidence so the test measures goal attention rather than reproducing the full dataset's large payment-volume imbalance.

```text
R000003 R000004 R000008 R000012 R000013 R000021
R000025 R000104 R000029 R000115 R000031 R000123
R000032 R000126 R000040 R000130 R000041 R000142
R000068 R000180 R000072 R000211 R000084 R000212
R000085 R000213 R000110 R000217 R000117 R000234
R000141 R000239 R000151 R000244 R000160 R000225
```

Both runs use `deepseek-v4-pro`, `zh-CN`, one batch, 36/36 analyzed Reviews, and `sampling_strategy=NONE`. Before analysis and after persistence, the exact Chinese Goal string was asserted unchanged. The mock provider test also verifies that `analysis_goal` exists in every Topic, Finding, and consolidation request payload.

### Goal A

- Run ID: `RUN-P3-GOAL-A-ACCEPTED`
- Goal: `重点分析订阅价格、免费功能减少和低评分付费体验。`
- Analysis time: `2026-08-14T04:08:14.959824+00:00`

Ordered leading Topics:

1. `订阅价格过高与收费不透明`
2. `免费功能减少与强制付费`
3. `低评分付费体验与AI生成内容质量差`
4. `个性化设置失效与锻炼计划不合理`

Leading Finding Candidates:

1. `订阅价格过高且收费不透明`
2. `免费功能减少与强制付费`
3. `低评分付费体验与AI生成内容质量差`

### Goal B

- Run ID: `RUN-P3-GOAL-B-ACCEPTED`
- Goal: `重点分析训练内容、动作设计、课程难度和使用体验。`
- Analysis time: `2026-08-14T04:09:12.591349+00:00`

Ordered leading Topics:

1. `训练内容与动作设计问题`
2. `个性化与避免部位失效`
3. `课程难度与强度不足`
4. `使用体验与功能建议`
5. `付费模式与订阅问题`

Leading Finding Candidates:

1. `每日训练计划重复且不均衡`
2. `AI生成训练内容质量低下`
3. `避免部位设置未生效`
4. `课程强度不足`
5. `声音提示不够灵活`
6. `计时方式不灵活`

### Comparison decision

The inputs and provider configuration are identical while the leading semantic results switch from subscription/payment to workout content/design/difficulty/usability. This, combined with deterministic request-payload tests, demonstrates that Analysis Goal participates in the runtime Prompt and is not only persisted as metadata.

During acceptance, earlier command-line attempts were excluded because PowerShell converted inline Chinese Goal text into question marks. The accepted runs construct the exact Unicode strings and assert their persistence round trip. Earlier full-250 goal runs were also excluded from the final comparison because the input distribution was too imbalanced to isolate ranking behavior. These excluded runs are not used as PASS evidence.

## 6. Unknown-domain generalization

### Input

- Fixture: `sample_data/phase3_music_reviews.json`
- Run ID: `RUN-1CBE3DC31736`
- 25 English Music App Reviews, five each for offline playback, lyrics, playlists, audio quality, and recommendations
- Output language: `en-US`
- Analysis Goal: `Discover the most important music listening and library-management problems.`

### Actual result

1. `Offline playback reliability` (5 Review IDs)
2. `Lyrics synchronization and display` (5)
3. `Playlist management problems` (5)
4. `Audio quality and playback glitches` (5)
5. `Music discovery and recommendations` (5)

The five Finding Candidates match those five review-derived problem families. Original Review text was unchanged. No `workout`, `exercise`, `fitness`, or subscription-paywall term appeared. A production-code scan found zero occurrences of the expected acceptance topic strings in `backend/app/**/*.py`.

## 7. Multilingual input and output language

### Input

- Fixture: `sample_data/semantic_smoke_reviews.json`
- Same 12 Reviews in both runs: 6 `en-US` and 6 `zh-CN`
- Original `Review.text` list captured before analysis and compared after analysis

### `zh-CN` result

- Run ID: `RUN-406ACFB35A90`
- 12/12, one batch, `deepseek-v4-pro`
- Topics: `离线下载与播放问题`, `播放队列顺序混乱`, `字幕与音频不同步`, `重复通知`, `睡眠定时器失效`, `车载控制延迟`
- Every Topic name contains Chinese text.

### `en-US` result

- Run ID: `RUN-24EA5C634101`
- 12/12, one batch, `deepseek-v4-pro`
- Topics: `Offline playback failures`, `Queue order instability`, `Transcript synchronization issues`, `Duplicate notifications`, `Sleep timer malfunction`, `Bluetooth control latency`
- No Topic name contains Chinese text.

Both runs passed exact Review-text equality checks. Output-language selection changes generated analysis only and never translates source Reviews.

## 8. Review ID grounding

The `CorrectingInvalidIdProvider` test returns `R999999` on its first Topic response.

Actual behavior:

1. Pydantic accepts the structural object.
2. Current-batch allowlist validation raises `INVALID_REVIEW_ID`.
3. A bounded correction retry is issued.
4. The corrected response is accepted.
5. The persisted `IngestionResult.model_dump_json()` is asserted not to contain `R999999`.

Cross-run IDs, disallowed batch IDs, duplicate candidate IDs, and consolidation lineage loss have separate deterministic tests. No hallucinated Review ID is silently saved.

## 9. Multi-batch consolidation

The official baseline supplies the real 200+ scenario:

| Metric | Value |
|---|---:|
| Reviews | 250 |
| Batches | 10 |
| Batch Topic Candidates | 58 |
| Consolidated Topics | 15 |
| Batch Finding Candidates | 49 |
| Consolidated Finding Candidates | 33 |
| Ad-related batch Topics | 10 |
| Global ad Topics | 1 |
| Global Topic Review-ID union preserved | Yes |
| Global Finding Review-ID union preserved | Yes |

The ad-related batch labels included `广告体验差`, `广告干扰`, `广告体验`, `广告与重定向干扰`, and `广告过多`; the final global Topic is `广告体验差`. Review IDs may move to a better semantic Topic during consolidation, but none disappear from the global Topic/Finding lineage unions.

The deterministic 205-Review mock test additionally forces nine batches with the same semantic topic, asserts one final Topic and one final candidate, and asserts all 205 Review IDs remain in both outputs.

## 10. Runtime LLM verification

`create_llm_provider(Settings())` returned:

```text
class: DeepSeekProvider
provider_name: deepseek
model: deepseek-v4-pro
base_url: https://api.deepseek.com
is_mock: false
```

Each real run has a new `analysis_time`, provider/model metadata, batch audit artifacts, and dataset-specific output. The Music result was created through JSON ingestion and a new runtime model call; it was not marked or loaded as `CACHED RESULT` or `DEMO RESULT`. Mock providers are used only inside deterministic automated tests.

## 11. Failure verification

### Invalid API key

The provider-level test simulates a DeepSeek HTTP 401 response. The provider emits non-retryable `LLM_AUTHENTICATION_FAILED`. The service-level test verifies:

- one provider attempt only;
- run status `FAILED`;
- `last_successful_stage=CLEANING_AND_NORMALIZATION`;
- all three cleaned Reviews remain persisted;
- `semantic_analysis is None`;
- the authentication error is recorded;
- no Topic or Finding Candidate is fabricated.

### Provider timeout

The timeout test raises `LLM_TIMEOUT` through the provider boundary with retry limit 2. It verifies:

- exactly three total attempts;
- run status `FAILED`;
- cleaned Reviews remain persisted;
- `semantic_analysis is None`;
- the timeout error and three failed attempts are recorded;
- no fake result is generated.

## 12. Human evidence spot check

Selection method: `random.Random(20260814).sample(...)` over the 33 baseline Finding Candidates. Excerpts are shortened for this report. Result: five of five claims have direct surface support.

### 1. 应用并非免费且订阅价格过高

- Review IDs: `R000151`, `R000160`
- `R000151`: “...you have to pay to subscribe.”
- `R000160`: “love everything but the price (used to be free).”
- Spot-check: claim is broadly supported.

### 2. 广告无法退出

- Review IDs: `R000002`, `R000035`, `R000048`, `R000055`, `R000073`, `R000101`, `R000133`, `R000143`, `R000146`, `R000155`, `R000167`, `R000168`, `R000170`, `R000171`, `R000178`, `R000186`, `R000190`, `R000195`, `R000198`, `R000222`, `R000237`, `R000247`
- `R000002`: “Even after you watch the 90 second ads, there’s no way to get out of it...”
- `R000048`: “the app will close and the Shein website will open...”
- Spot-check: claim is broadly supported.

### 3. 应用并非真正免费，用户被迫付费或观看广告

- Review IDs: `R000178`, `R000179`, `R000187`, `R000199`
- `R000179`: “Says it’s free... then gives you no way to continue without paying...”
- `R000187`: “After filling everything out you find out the app is not free.”
- Spot-check: claim is broadly supported.

### 4. 邀请朋友注册后未获得承诺的免费积分

- Review IDs: `R000229`
- `R000229`: “they offered the free credits if you invite a friend... I did that and then nothing happened.”
- Spot-check: claim is broadly supported, but it is single-review evidence and receives no Phase 4 sufficiency status here.

### 5. AI生成内容不真实

- Review IDs: `R000003`, `R000010`, `R000018`, `R000123`, `R000180`
- `R000010`: “It’s all AI slop and you have to pay.”
- `R000018`: “not some cheesy AI mockups showing unrealistic images...”
- Spot-check: claim is broadly supported.

## 13. Automated and browser verification

### Backend

```text
56 passed
```

Coverage added during acceptance includes a 205-Review consolidation case, explicit invalid-credential preservation, provider HTTP 401 classification, and a persisted assertion that `R999999` never survives correction.

### Frontend build

TypeScript checks and Vite production build passed. The terminal semantic stage now displays `Analysis complete` / `分析完成` at 100% instead of showing an active consolidation label.

### Playwright

Browser scenario:

```text
Upload phase3_music_reviews.json
-> 25/25 deterministic ingestion
-> set Analysis Goal
-> select en-US output
-> start real DeepSeek semantic analysis
-> display five Music Topics and Finding Candidates
-> open source Review IDs and excerpts
-> switch UI language
-> verify final 100% state and Backend Connected
```

Result: PASS. Browser console contained 0 errors and 0 warnings. Local screenshot: `output/playwright/phase3-acceptance-music.png` (ignored by Git as a temporary test artifact).

## 14. Known limitations

- Phase 3 candidate grounding proves identifier validity and performs only a human surface check. Semantic support, conflict, ambiguity, sufficiency, evidence strength, confidence, and final Finding status belong to Phase 4.
- Runtime model output is non-deterministic. Goal acceptance therefore uses a fixed balanced input and records exact run IDs/results rather than expecting byte-identical output on every future run.
- The U.S. RSS feed is not a documented stable Apple API and exposes only a bounded recent-review window.
- DeepSeek availability, quota, regional/network access, and model behavior are external dependencies.
- A single FastAPI process performs in-process background work. Completed batches and consolidation rounds are resumable, but an active provider request is interrupted by process termination.
- The React page does not restore an analysis workspace after a full page reload because route/run restoration is deferred; persisted backend results remain available through the run APIs.

## 15. Final gate

All Phase 3 core acceptance scenarios pass. Phase 3 may be marked complete. Phase 4 has not started.
