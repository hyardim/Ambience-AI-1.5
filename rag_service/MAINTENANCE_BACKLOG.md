# Maintenance Backlog

Items intentionally deferred while we finish correctness and code review passes.

## Ingestion

- `src/ingestion/store.py`: reduce per-chunk commits to batched or per-document transactions for better ingestion performance and clearer partial-failure handling.
- `src/ingestion/store.py`: replace JSON-string metadata comparisons with a less brittle semantic comparison strategy.
- `src/ingestion/pipeline.py`: review whether `discover_pdfs(..., since=...)` should include same-day files with `>=` rather than strict `>`.

## Retrieval

- `src/retrieval/retrieve.py`: move retrieval debug artifact output onto shared `path_config` instead of a relative path.
- `src/retrieval/query.py` and `src/ingestion/embed.py`: consider unifying embedding model caching so query-time and ingestion-time embedding do not keep separate caches.
