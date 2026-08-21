# Sample review datasets

All files in this directory are synthetic **SAMPLE DATA** for local verification. They are not live App Store reviews, cached model output, or proof of a U.S. storefront collection.

| File | Purpose | Input format |
| --- | --- | --- |
| `workout_compatible_sample.json` | Workout-domain compatible input without any application-specific processing rule. | JSON `{ "reviews": [...] }` |
| `music_unknown_domain.csv` | Unknown-domain CSV used to verify dynamic Music topics instead of Workout taxonomy. | CSV with canonical fields |
| `mixed_language_reviews.json` | Mixed English and Chinese Music reviews with enough repeated evidence for a full E2E. | JSON array |
| `semantic_smoke_reviews.json` | Smaller mixed English and Chinese Podcast reviews for semantic smoke checks. | JSON `{ "reviews": [...] }` |
| `sample_reviews.csv` | Dirty/duplicate data: duplicate source ID, blank text, and invalid rating. | CSV with canonical fields |
| `conflicting_evidence_reviews.json` | Material positive and negative feedback about the same redesign. | JSON `{ "reviews": [...] }` |
| `insufficient_evidence_reviews.json` | A single relevant Review for insufficiency behavior. | JSON `{ "reviews": [...] }` |
| `phase3_music_reviews.json` | Larger Music-domain topic-discovery fixture. | JSON `{ "reviews": [...] }` |
| `sample_reviews.json` | Minimal JSON ingestion example. | JSON `{ "reviews": [...] }` |

## Use

Start the application, choose CSV or JSON, select the matching file, optionally provide an Analysis Goal, and click **Start Analysis**. Live semantic stages require a configured DeepSeek API key. Deterministic ingestion and cleaning do not.

Canonical input fields are `id`, `text`, `title`, `rating`, `version`, `author`, `date`, `language`, `app_id`, and `storefront`; only `text` is required. See the repository `README.md` for aliases and safety limits.
