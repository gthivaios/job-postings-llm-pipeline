# Stage 2: Translation

Translates each posting's `title`, `job_type` and `description` to English with an open-weight LLM through [OpenRouter](https://openrouter.ai), and stores the result in `unified_postings`.

## Output columns

| Column | Content |
|---|---|
| `en_title` | Translated title |
| `en_job_type` | Translated job type (NULL if the posting has none) |
| `en_description` | `en_title`, `en_job_type` and the translated description, separated by blank lines |
| `translation_model` | OpenRouter model that produced it |
| `translated_at` | When it was written |
| `translation_cost_usd` | Cost of the LLM calls made for this posting (0 when served from cache) |
| `translation_latency_ms` | Total latency of those calls |

`en_description IS NULL` means "not translated yet". Re-running the stage continues where it stopped.

## How it works

1. **Select:** postings scraped on one day (optionally one portal, or the first N) that are not translated yet.
2. **Prepare:** `normalize_text` (Unicode normalisation, URLs and emojis removed, whitespace collapsed) on each field, then `split_text_into_chunks` on the description. Chunking keeps each request within the context window of small models.
3. **Deduplicate and cache:** each distinct text is translated once. Results are stored in `llm_cache`, keyed by `sha256(model | prompt version | text)`. A job type such as `Πλήρης απασχόληση` that appears on thousands of postings is paid for once, and a crashed run restarts for free.
4. **Translate in parallel:** only the LLM calls run concurrently (`TRANSLATE_WORKERS`); all database work stays in one thread. Failed calls are retried with backoff. A posting with a failed segment stays NULL and is picked up on the next run.
5. **Write:** one transaction per 50 postings, so progress survives interruptions.

Cost is charged once: when several postings share a text, the first one carries its cost. `SUM(translation_cost_usd)` therefore equals what was actually spent.

## Run it

```bash
uv run python -m jobpipe.translate --list-days                  # postings per day, and progress
uv run python -m jobpipe.translate --date 2026-04-01 --dry-run  # how much work, no API calls
uv run python -m jobpipe.translate --date 2026-04-01 --limit 20 # small first test
uv run python -m jobpipe.translate --date 2026-04-01            # the whole day
```

| Option | Meaning |
|---|---|
| `--date` | Day to translate, by `scraped` (required) |
| `--portal` | Only this portal |
| `--limit` | At most N postings |
| `--model` | `phi-4` (default), `qwen-2.5-7b`, `mistral-7b`, `gpt-oss-120b`, or any OpenRouter model id |
| `--workers` | Parallel LLM calls (default `TRANSLATE_WORKERS`) |

The cache is per model and per prompt version. To compare a model on the same day, reset the day first:

```sql
UPDATE unified_postings SET en_description = NULL WHERE DATE(scraped) = '2026-04-01';
```

## Tracing with Opik

Every LLM call can be traced in [Opik](https://www.comet.com/docs/opik/): input text, output, latency, token counts and cost, plus metadata (segment type, posting `uid`s, prompt version). OpenRouter reports the actual charged cost in every response, and that value is what Opik shows.

Set `TRACING=opik` in `.env`, then either:

- **Opik Cloud (free):** create an account at comet.com/opik and set `OPIK_API_KEY` and `OPIK_WORKSPACE`; or
- **Self-hosted:** run Opik locally ([instructions](https://www.comet.com/docs/opik/self-host/local_deployment)) and set `OPIK_URL_OVERRIDE=http://localhost:5173/api`.

With `TRACING=none` (the default) the stage runs the same, and latency and cost are still recorded in the database and printed in the run summary.

Each translation call is one trace (`translate_text`) with the LLM request as a child span (`llm_call`). Filter by the tag `translate` or by model.

## Models

| Alias | OpenRouter id | Notes |
|---|---|---|
| `phi-4` | `microsoft/phi-4` | Default |
| `qwen-2.5-7b` | `qwen/qwen-2.5-7b-instruct` | |
| `mistral-7b` | `mistralai/mistral-7b-instruct` | |
| `gpt-oss-120b` | `openai/gpt-oss-120b` | Reasoning model; run with low reasoning effort to limit cost and latency |
