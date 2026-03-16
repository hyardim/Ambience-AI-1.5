# RAG Service Tasks

This list is for improvements worth considering after the current cleanup pass.
Items are grouped by confidence level so we can separate clear issues from
benchmark-driven optimizations.

## High Priority

### Apply chunk overlap within long sections
- File: `src/ingestion/chunk.py`
- Current issue: overlap is carried between section groups, but long sections
  split into multiple sub-chunks do not clearly preserve internal overlap.
- Why it matters: important context can be cut at chunk boundaries, especially
  in dense guideline prose where the key recommendation spans two adjacent
  chunks.

### Drive specialty/source validation from `sources.yaml`
- File: `src/ingestion/metadata.py`
- Current issue: `VALID_SPECIALTIES` and `VALID_SOURCE_NAMES` are hard-coded.
- Why it matters: every new specialty or source currently requires code edits
  instead of config-only onboarding.

### Add persistent retrieval telemetry
- Files: `src/retrieval/retrieve.py`, `src/api/services.py`, optionally
  `src/retrieval/rerank.py`
- Current issue: debug artifacts are optional and ad hoc; there is no durable
  record of retrieval stage counts/scores/latency over time.
- Why it matters: regressions in retrieval quality or latency are hard to spot
  once the corpus changes.

### Add higher-fidelity retrieval integration tests
- Area: `tests/retrieval/`, `tests/api/`
- Current issue: unit coverage is strong, but many tests still mock lower-level
  pieces rather than exercising realistic ingest -> retrieve flows.
- Why it matters: index/schema/config drift is easier to miss without more
  end-to-end retrieval tests.

### Revisit lexical overlap gating in API filtering
- File: `src/api/services.py`
- Current issue: `filter_chunks()` requires `has_query_overlap(query, chunk)`
  after retrieval. This can remove semantically relevant chunks that match via
  embeddings or abbreviation expansion rather than surface-token overlap.
- Why it matters: good results can be dropped late in the pipeline, especially
  for synonyms, abbreviations, and paraphrased guideline text.

### Fix metadata semantics in API chunk shaping
- File: `src/api/services.py`
- Current issue: `_cited_result_to_chunk()` currently sets
  `metadata["source_path"] = citation.source_url`.
- Why it matters: URL and filesystem path are different concepts; this works as
  a truthy placeholder today, but it is semantically wrong and can confuse later
  filtering or UI logic.

### Align no-evidence handling across `/ask`, `/answer`, and `/revise`
- Files: `src/orchestration/pipeline.py`, `src/api/routes.py`,
  `src/generation/prompts.py`
- Current issue: the service has multiple user-facing answer paths with slightly
  different fallback behavior when retrieval is weak or empty.
- Why it matters: product behavior should be consistent when evidence is absent,
  especially for safety-sensitive clinical questions.

### Add stronger retry observability
- Files: `src/jobs/retry.py`, `src/api/routes.py`
- Current issue: retry lifecycle is logged, but there is no compact summary of
  retry rates, terminal failures, queue age, or provider-specific failure modes.
- Why it matters: retry queues can silently degrade user experience if jobs pile
  up or if one provider starts failing more often.

## Medium Priority

### Benchmark stronger medical embedding models
- Files: `configs/ingestion.yaml`, `src/retrieval/query.py`,
  `src/ingestion/embed.py`
- Candidates to evaluate:
  - `pritamdeka/S-PubMedBert-MS-MARCO`
  - other sentence-embedding models tuned for biomedical retrieval
- Why it matters: current `all-MiniLM-L6-v2` is general-purpose and may leave
  retrieval quality on the table for specialist terminology.
- Note: this should be benchmarked, not swapped blindly.

### Increase or make configurable the effective query token limit
- File: `src/retrieval/query.py`
- Current issue: `MAX_TOKENS = 512` may be restrictive for long clinical cases.
- Why it matters: detailed case descriptions, patient context, and uploaded file
  context can make clinically useful queries longer than general search queries.
- Note: any increase should be paired with latency monitoring.

### Replace rough token estimation with tokenizer-based validation
- File: `src/retrieval/query.py`
- Current issue: token limit enforcement uses `len(words) * 1.3`, which is only
  a heuristic.
- Why it matters: borderline queries may be rejected or accepted inaccurately.

### Expand abbreviation / synonym coverage
- File: `src/retrieval/query.py`
- Current issue: the medical expansion dictionary is helpful but still small.
- Why it matters: retrieval recall depends heavily on abbreviation handling in
  real clinical questions.
- Note: this is best done from observed query data rather than by guessing.

### Make reranker model selection configurable and benchmark domain-specific options
- File: `src/retrieval/rerank.py`
- Current issue: reranker model is still hard-coded to a general-purpose
  cross-encoder.
- Why it matters: embedding quality and reranking quality should evolve
  together; a medical reranker may improve final ranking even if embeddings stay
  the same.

### Calibrate local/cloud routing with real traffic
- Files: `src/generation/router.py`, `src/api/routes.py`
- Current issue: routing weights and thresholds are heuristic. Complexity,
  prompt-size, ambiguity, and severity signals are sensible, but not yet tuned
  against actual quality/cost outcomes.
- Why it matters: poor calibration can overuse cloud for simple cases or keep
  difficult cases on the local model too long.

### Add route-decision telemetry and outcome analysis
- Files: `src/generation/router.py`, `src/api/services.py`,
  `src/api/routes.py`
- Current issue: route decisions are logged, but there is no structured review
  loop tying provider choice to retrieval quality, retries, latency, or user
  outcomes.
- Why it matters: routing logic improves fastest when it can be evaluated
  against real requests rather than intuition.

### Make prompt selection easier to evaluate and version
- Files: `src/generation/prompts.py`, `src/config/llm.py`
- Current issue: prompt variants exist, but prompt evolution still depends on
  manual code changes and ad hoc comparison.
- Why it matters: prompt changes affect clinical style, citation behavior, and
  fallback wording. They should be easier to compare deliberately.

### Reduce public-surface drift between `/ask` and the main API
- Files: `src/api/ask_routes.py`, `src/api/routes.py`,
  `src/orchestration/pipeline.py`, `src/orchestration/generate.py`
- Current issue: `/ask` still uses a partially separate orchestration and
  generation path even though more of the shared core has been unified.
- Why it matters: two public answer paths increase the chance of subtle logic
  drift in prompt style, no-evidence behavior, and model-call semantics.

### Unify generation call semantics across orchestration and main API
- Files: `src/orchestration/generate.py`, `src/generation/client.py`
- Current issue: orchestration still has a separate synchronous chat-completion
  wrapper instead of fully reusing the main generation client path.
- Why it matters: fallback rules, timeout behavior, auth handling, and response
  parsing should stay identical across service entrypoints.

### Add better low-evidence strategy for answer generation
- Files: `src/api/routes.py`, `src/generation/prompts.py`,
  `src/api/services.py`
- Current issue: the system currently has a binary “enough chunks vs no chunks”
  flow, but not a richer strategy for weak-evidence cases.
- Why it matters: low-confidence retrieval is common in clinical work. The
  service should make it easier to abstain, hedge, or explicitly separate
  guideline-backed content from general context.

### Revisit score-threshold semantics for keyword-only hits
- Files: `src/retrieval/filters.py`, `src/retrieval/fusion.py`
- Current issue: thresholding applies only to `vector_score`; chunks that appear
  only in keyword search bypass the similarity gate.
- Why it matters: this can be useful for recall, but it also means weak lexical
  hits can survive more easily than weak vector hits.
- Note: this is a strategy decision, not an outright bug.

## Lower Priority / Benchmark-Driven

### Evaluate HNSW vs IVFFlat for current corpus size and growth
- Area: pgvector indexing strategy
- Why it matters: HNSW is a good default, but the best choice depends on corpus
  size, write frequency, latency target, and memory budget.

### Tune chunk size and overlap using real query logs
- Files: `src/ingestion/chunk.py`, `configs/ingestion.yaml`
- Why it matters: chunking should be optimized against actual question patterns
  and retrieval outcomes, not just general heuristics.

### Add alerting on retrieval-quality drift
- Area: monitoring/ops
- Why it matters: once retrieval telemetry exists, low-score trends and empty
  result rates can be monitored automatically.

### Add alerting on retry backlog and provider degradation
- Area: monitoring/ops
- Why it matters: once retry telemetry exists, queue depth, job age, and
  provider-specific failure spikes should be visible before they become user
  incidents.

## Strategy / Evaluation Tasks

### Build a small labelled retrieval evaluation set
- Purpose: benchmark embeddings, rerankers, chunking parameters, and score
  thresholds on real clinical questions.
- Why it matters: several proposed changes are plausible wins, but evaluation
  data is what distinguishes a real improvement from churn.

### Review `/ask` vs `/query` product intent periodically
- Area: `src/api/ask_routes.py`, `src/api/routes.py`
- Current state: both now share much more of the same core, but they are still
  separate public entrypoints.
- Why it matters: if only one path is truly needed long-term, simplifying the
  public surface will reduce maintenance load.

### Create answer-quality review criteria, not just retrieval benchmarks
- Area: generation + API
- Purpose: evaluate answer usefulness, citation faithfulness, abstention
  behavior, and low-evidence handling on representative clinical questions.
- Why it matters: retrieval improvements do not automatically produce better
  final answers, and routing/prompt changes need a quality bar too.
