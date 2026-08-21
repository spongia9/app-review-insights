# Cached demonstration result

`workout_demo.json` is a complete, previously generated Workout for Women analysis packaged for offline review. It includes cleaned Reviews, dynamic Topics, Finding Candidates, evidence-validated Findings, Requirements, a VersionPlan, Structured PRD and rendered Markdown, TestCases, final traceability, and run audit artifacts.

The artifact contains immutable provenance under `cached_demo`:

```json
{
  "CACHED_DEMO": true,
  "source": "apple_customer_reviews_rss",
  "collection_time": "...",
  "model_provider": "deepseek",
  "model_name": "...",
  "analysis_time": "..."
}
```

The UI always labels it **Cached Demo Result / 示例缓存结果**. Loading it does not call Apple or DeepSeek, does not require an API key, and does not change the original collection or analysis timestamps. It must not be presented as a new live result.

To regenerate this tracked artifact from another complete local run:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\export_cached_demo.py <RUN_ID>
```

Review the provenance and validate the complete backend suite before committing a replacement.
