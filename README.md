# LaienTech iOS App Review Analysis and Version Planning Assessment

## Background

This assessment uses the following real iOS app as the primary development and demonstration example:

https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684

If you have access to an overseas network environment, use the U.S. App Store link above. If not, and the U.S. link cannot be opened or redirects, use the China App Store link only to open the app detail page:

https://apps.apple.com/cn/app/workout-for-women-home-gym/id839285684

Regardless of which link is used to open the page, the review data used in this assessment must come from the U.S. App Store storefront.

You are expected to complete a full product analysis workflow around App Store user reviews, covering data collection, review cleaning, review classification, issue analysis, version planning, PRD writing, and test case design. The final results should be presented through a runnable UI.

This assessment focuses on the candidate's vibe coding ability. Candidates should use vibe coding to complete the full process: collecting data, cleaning and analyzing reviews, abstracting product requirements, planning versions, designing test cases, and productizing the analysis workflow into an interactive experience.

## Objective

Build a runnable tool or web application. In the UI, the user should be able to enter a valid U.S. App Store app link. Use the following link as the primary example:

```text
https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684
```

The user should also be able to provide an analysis goal or constraint, such as focusing on subscription conversion, workout usability, a specific app version, or low-rating reviews. The system must not depend on app-specific hard-coded categories, findings, requirements, or test cases.

After the user clicks "Start", the system should automatically complete the following workflow and display the results in the UI:

1. Determine the analysis scope based on the user's goal and the available data.
2. Collect review data for the app.
3. Clean, deduplicate, and structure the review data.
4. Dynamically classify and analyze the reviews, rather than relying only on fixed keyword mappings or a predefined issue taxonomy.
5. Evaluate whether the available evidence is sufficient, and identify conflicting feedback, uncertainty, and data limitations.
6. Create an update plan based on the analysis, produce a PRD, and split the scope into multiple versions when necessary.
7. Generate test cases based on the PRD, with each test case linked to its requirement and source user reviews.
8. Validate the traceability chain from reviews to findings, requirements, and test cases. Unsupported conclusions must be removed, revised, or explicitly marked as assumptions.
9. Display the execution progress in the UI, including the stages, intermediate results, validation results, errors, and revisions.
10. Display the interim and final deliverables, including raw reviews, cleaned data, classification results, findings, PRD drafts, and test case drafts.

## AI Requirements

- At least one core semantic task must be model-driven. Suitable tasks include dynamic topic discovery, issue consolidation, evidence-grounded analysis, requirement generation, or test case generation. Implementing all semantic analysis only through fixed keywords, regular expressions, lookup tables, or manually predefined mappings does not meet this requirement.
- Deterministic rules are encouraged where they are appropriate, including data collection, deduplication, field normalization, validation, and safety checks. The submission should explain why rules, statistical methods, or language models were chosen for each stage.
- Every major finding must include its source review IDs or excerpts, supporting sample count, confidence or uncertainty, and any material conflicting evidence. Model-generated conclusions must remain distinguishable from deterministic statistics.
- The submission must document the model and provider used, the main prompts or tool definitions, model configuration, failure-handling strategy, and measures used to reduce hallucinations and unsupported conclusions.
- Hosted APIs, local models, or other model runtimes may be used. Secrets must be supplied through environment configuration and must not be committed to the repository.

## Deliverables

Submit a GitHub project link and ensure the project can run locally.

The GitHub project should include complete source code, dependency configuration, running instructions, an explanation of the data collection method, and any necessary sample output or cached data so that interviewers can review the results even when external network access is unavailable. Cached results must be clearly labeled and must not replace the ability to process a previously unseen input when the required network and model configuration are available.

The application must also support importing review data from a documented JSON or CSV format. During evaluation, interviewers may provide a different valid App Store link, a previously unseen compatible review dataset, or a new analysis goal. The submission will be evaluated on whether it can produce grounded results without app-specific hard coding.

The GitHub project should preserve a complete commit history to show the candidate's implementation process, iteration process, and use of vibe coding.

## Technical Requirements and Notes

- There is no restriction on the tech stack.
- You may use frontend frameworks, backend frameworks, data analysis libraries, visualization libraries, natural language processing models, or large language model APIs.
- You may use public APIs or third-party data collection libraries, but you must clearly explain the data source and its limitations.
- Pay attention to request rate limits and avoid placing abnormal load on the target site.
- Provide a sample environment file or equivalent configuration instructions, but do not include API keys or other secrets.
- A non-runnable document-only submission is not acceptable.

## Current Implementation Notes — Phase 3

Phase 3 adds runtime, model-driven semantic analysis after deterministic ingestion and cleaning. The configured DeepSeek model receives bounded batches of normalized Review fields plus the optional analysis goal. It dynamically discovers dataset-specific Topics, extracts structured `FindingCandidate` user problems, and performs a model-driven cross-batch consolidation. These are explicitly unvalidated candidates; Phase 4 evidence support/conflict/sufficiency evaluation is not implemented yet.

### Runtime LLM configuration

Configure the untracked project-root `.env`:

```text
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-v4-flash
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=<your DeepSeek API key>
LLM_REVIEW_BATCH_SIZE=25
LLM_MAX_RETRIES=2
LLM_REQUEST_TIMEOUT_SECONDS=120
LLM_MAX_OUTPUT_TOKENS=4096
LLM_TEMPERATURE=0.2
LLM_THINKING_ENABLED=false
LLM_TRUST_ENVIRONMENT_PROXY=false
```

Obtain the key from the DeepSeek platform. The key is loaded as a secret and is never logged. JSON Output is requested from DeepSeek, the expected Pydantic JSON Schema is included in each prompt, and every response is validated again locally. `LLM_TRUST_ENVIRONMENT_PROXY=false` avoids inheriting broken system proxy settings; set it to `true` only when the local network requires a correctly configured proxy.

### Prompt and batching strategy

Prompts live in `backend/app/prompts/`: `topic_discovery.md`, `finding_candidate.md`, and `topic_consolidation.md`. They require generated text in the resolved Analysis Output Language and prohibit fabricated reviews/IDs, requirements, PRDs, version plans, test cases, and final evidence claims.

All cleaned reviews are analyzed in deterministic ordered batches of `LLM_REVIEW_BATCH_SIZE`; Phase 3 does not sample (`sampling_strategy=NONE`). Only Review ID, rating, title, text, version, language, and date are sent—never `raw_data`. Batch responses may cite only the current batch; consolidation may cite only the current run and must preserve the union of source Review IDs and batch IDs. Invalid JSON/schema, invalid IDs, timeouts, and retryable provider failures receive at most `LLM_MAX_RETRIES` correction retries.

### Language and transparency

UI locale and Analysis Output Language are independent. The request supports `FOLLOW_UI`, `zh-CN`, and `en-US`; source `Review.text` is never translated or modified. The run records total/analyzed reviews, batch size/count, sampling strategy, provider/model, analysis goal, selected/resolved output language, stage progress, revisions, errors, and run-scoped topic/finding/consolidation audit artifacts.

### Phase 3 limitations

- `FindingCandidate` is `UNVALIDATED_CANDIDATE`, not the final `Finding` model.
- No semantic support/conflict/sufficiency validation or final evidence status is produced.
- A single FastAPI worker runs background tasks in-process; process restarts can interrupt an active model request, while prior persisted stage output remains inspectable.
- DeepSeek API availability, account quota, regional/network access, and model behavior are external dependencies.
- Requirement, VersionPlan, PRD, TestCase, and final traceability generation remain unimplemented.

Run the real-model smoke test without exposing the key:

```powershell
cd backend
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe scripts\real_llm_smoke.py
```

## Phase 2 Data Foundation

The current application implements deterministic review ingestion and cleaning for three inputs: a U.S. App Store URL, CSV upload, and JSON upload. All three produce the same run-scoped `Review` model before any semantic analysis. Phase 2 does not call an LLM.

### App Store source and limitations

Live collection uses Apple's storefront-specific public customer-review RSS JSON feed:

```text
https://itunes.apple.com/us/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json
```

The provider accepts only `https://apps.apple.com/us/app/.../id{numeric_id}` input, requests the `us` feed, and records `source`, `storefront`, `collection_time`, and `source_limitations`. This is not visible-page HTML scraping. The public RSS feed is not documented as a stable API, may change or become unavailable, exposes only recent feed pages, and can be affected by network/rate limits. A failure is reported explicitly; the application never fabricates reviews or silently substitutes sample data.

### CSV contract

CSV must use UTF-8 or UTF-8 with BOM and include a header. `text` is required. Canonical fields are `id`, `title`, `text`, `rating`, `version`, `author`, `date`, `language`, `app_id`, and `storefront`. Documented aliases are:

```text
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

### JSON contract

JSON must use UTF-8 and be either an array of review objects or exactly `{ "reviews": [...] }`. Review objects use the same canonical fields and aliases as CSV. Arbitrary top-level wrappers are rejected.

### Limits and deterministic cleaning

Defaults are 10 MiB per upload and 10,000 records, configurable with `MAX_UPLOAD_BYTES` and `MAX_REVIEW_ROWS`. Cleaning collapses whitespace without changing meaning, normalizes optional strings/language/date/rating, rejects empty text and invalid typed fields, retains `raw_data`, and assigns stable run-local IDs such as `R000001`. Deduplication first uses `(source, source_review_id)`; records without a source ID use a SHA-256 fingerprint of normalized title, text, and rating. No embeddings, semantic similarity, or LLM deduplication are used.

`sample_data/` contains clearly labeled synthetic sample files for development and offline verification. They are not live or cached App Store results.

### Local run

Use Python 3.9+ and Node.js 20+.

```powershell
# project root
Copy-Item .env.example .env

# backend
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# frontend (another terminal, from project root)
cd frontend
npm.cmd install
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. The health endpoint is `http://127.0.0.1:8000/api/health`. Run backend tests with `.\.venv\Scripts\python.exe -m pytest` from `backend/`, and build the frontend with `npm.cmd run build` from `frontend/`.

## Evaluation Criteria

This assessment focuses on whether the candidate can turn real user reviews into an executable product plan. The evaluation will mainly consider:

- Whether the data is authentic and reproducible, with a clear explanation of its source and limitations.
- Whether review cleaning, classification, and analysis are reasonable, and whether they surface concrete user problems.
- Whether model-driven semantic analysis adds capability beyond fixed rules and generalizes to previously unseen reviews, apps, and analysis goals.
- Whether findings distinguish evidence, deterministic statistics, model-generated conclusions, uncertainty, and conflicting feedback.
- Whether the PRD is grounded in user problems, with clear requirement boundaries, priorities, and version planning.
- Whether the test cases cover the PRD and can be traced back to the corresponding user reviews.
- Whether the UI clearly presents the workflow and results, and whether the project can run locally with clear delivery instructions.

## Important Notes

- This is not merely a web scraping task, nor is it merely a UI presentation task.
- The core challenge is to identify problems from real user reviews and turn them into executable product requirements and test plans.
- Review data should not be collected by scraping only the visible content of the page. There are more appropriate ways to retrieve App Store review data; candidates are expected to explore them independently and explain their implementation.
- Requirements in the PRD must be traceable to specific user reviews.
- Test cases must be able to verify whether the corresponding requirements solve the problems raised in those reviews.
- The use of an AI coding assistant during implementation does not by itself satisfy the AI requirements. The submitted application must demonstrate model-driven semantic analysis at runtime.
- Interviewers may test the application with previously unseen data, mixed languages, duplicate or conflicting reviews, insufficient evidence, or temporary collection/model failures.
- If the amount of available data is limited or data collection is constrained, state this transparently in the results. Do not fabricate data.
