# M3 Research System report

## Status and scope

M3 brings the existing Olist analytical backend and metadata-driven visual analytics runtime into a controlled research workflow. M1 dataset adapter behavior and M2 visualization behavior remain unchanged by Task 6. Tasks 1–6 have implementation reports and independent approval recorded under `.superpowers/sdd/m3-research-system/reports/`; the M3 software milestone is complete under the deterministic test and offline-analysis scope described here.

The software supports the canonical conditions `turn_taking` and `revision_enabled`; `half_duplex` and `full_duplex_rrt` are accepted only as ingress aliases. Both conditions share the same data, tools, model, prompt, dashboard, ASR, and TTS. Runtime utterance roles are limited to `empty`, `backchannel`, `stop`, and `analytical_request`. Goal, Hypothesis, and Scope are post-hoc research codes only, never online control labels.

An accepted analytical request creates one node in a session-scoped request chain. A request may own several provider responses and tool follow-ups; those do not increase request count. Only acceptance while the prior request is in an active phase (`reasoning`, `tool_execution`, `committing`, or `speaking`) is an in-flight revision. ResponseProtocol remains the sole authority for tool admission, commit, and output publication.

## Execution and commit outcomes

Physical execution success is independent from public dashboard installation:

| Situation | `execution_status` | `commit_status` | `state_changed` | Public dashboard commit |
|---|---|---|---:|---:|
| Successful read-only batch | `succeeded` | `read_only` | `false` | No |
| Successful mutating no-op | `succeeded` | `no_change` | `false` | No |
| Successful changed draft | `succeeded` | `committed` | `true` | Exactly one |
| Failed batch, private draft discarded | `failed` | `failed` | `false` | No |
| Authority revoked before install | Actual execution outcome | `superseded` | `false` | No |
| Successful execution with dashboard CAS mismatch | `succeeded` | `conflicted` | `false` | No |

Only a real `dashboard.committed` Trace event with a batch ID counts as a public commit. Tool success, read-only results, no-change results, conflicts, failures, and supersession never imply a dashboard update. The frontend continues to install chart state only from the authorized `dashboard_commit` message. Superseded feedback is scoped to its request/batch and cannot clear a newer batch.

## Trace v2 and analyzer

Trace v2 records a frozen experiment context (`session_id`, pseudonymous participant/trial/task IDs, dataset, canonical condition), session-local `seq`, UTC `observed_at`, monotonic nanoseconds, correlation IDs, event name, and structured data. It does not persist raw audio. Without consent, transcript and arguments are redacted; the offline analyzer does not access consent-controlled transcript/arguments/audio/payload fields even when present.

Run the standard-library analyzer from the project root:

```powershell
python scripts/analyze_traces.py path/to/trace.jsonl
python scripts/analyze_traces.py path/to/trace.jsonl --output summary.json
python scripts/analyze_traces.py path/to/trace.jsonl --strict
```

Output is deterministic JSON schema version 1 with analyzer version, basename-only source, summary counts, per-session trial runs, and diagnostics. Each run includes the frozen context and these metrics:

| Metric | Definition |
|---|---|
| `duration_ms` | `session.closed.monotonic_ns - session.started.monotonic_ns`; if close is missing, last valid sequence-ordered timestamp is only a lower bound and `duration_complete=false`. |
| `request_count` | Unique request IDs from `user.request_received`; unmatched IDs may fall back to `request.received` / `revision.received`, with `request_count_fallback` diagnostic. Paired events do not double-count. |
| `in_flight_revision_count` | Unique `revision.received` request IDs with `data.in_flight=true`. `response.superseded` corroborates but is not another count. |
| `superseded_batch_count` / `superseded_call_count` | Unique Task 5 `batch.outcome` records with canonical `commit_status=superseded`, and unique `(batch_id, call_id)` pairs from their `data.call_ids`; reused call IDs in different batches count separately. |
| `dashboard_commit_count` | Unique batch IDs observed in `dashboard.committed`. |
| `time_to_final_state_ms` | Last accepted request's first explicit terminal lifecycle timestamp minus its `received_at_monotonic_ns`. Missing receive or terminal time yields null. |
| `revision_saving_windows_ms` | One entry per in-flight revision; only calculated from that revision receive timestamp and an actually observed `request.settled` for its exact `previous_request_id`. |
| `revision_saving_window_ms` | Scalar compatibility summary only when the session has exactly one in-flight revision; otherwise null because a multi-revision session has no single unambiguous value. |

All output durations are finite nonnegative milliseconds or null; source monotonic values are nanoseconds and absolute monotonic baselines are never emitted. A saving window is `old_request_settled_ns - revision_received_ns`; missing settlement, superseded-only lifecycle, a `response.done` event alone, an unrelated request settlement, or a negative delta never produces an estimated value. Negative deltas are diagnosed and return null. There is no counterfactual wait-time model.

Input is processed by physical line and retained in memory only as a metric-specific safe projection. Valid JSON on a final line without a newline is accepted. Malformed lines and invalid schema/context/timing/IDs are diagnosed and skipped; valid events are grouped by `session_id`, sorted by local `seq`, and exact safe-projection duplicates are idempotently discarded. Conflicting records at the same sequence report a diagnostic and the first physical record wins. Multiple sessions with the same `trial_id` stay separate so their clocks are never mixed. Normal mode recovers and returns zero when analysis completes; `--strict` still writes the report and returns nonzero if any diagnostic exists. Output cannot overwrite the input trace.

## Verification evidence

Task 6 added `scripts/analyze_traces.py`, `tests/test_trace_analyzer.py`, and a checked-in CLI fixture at `tests/fixtures/trace_v2_analyzer.jsonl`. The focused suite covers request/follow-up dedupe, revision timing/null cases, Task 5 outcome matrix, real commits, multiple sessions, disorder/gaps/duplicates/conflicts, malformed/truncated/v1 records, context/timing/ID validation, privacy, determinism, and CLI modes.

Latest verification:

| Command | Result |
|---|---|
| `python -m pytest tests/test_trace_analyzer.py -q` | 44 passed |
| `python -m pytest -q` | 277 passed; one existing Starlette/httpx deprecation warning |
| `npm test` (from `frontend`) | 63 passed |
| `npm run build` (from `frontend`) | Successful; existing 833.94 kB `embed` chunk warning |
| `python -m pytest tests/test_initial_dashboard.py::test_olist_initial_dashboard_materializes_against_real_data -q` | 1 passed using configured real Olist CSVs |
| `python scripts/analyze_traces.py tests/fixtures/trace_v2_analyzer.jsonl` | 1 trial run; 2 requests; 1 dashboard commit; duration 1000 ms; final request latency 100 ms; 0 diagnostics |
| `python -m py_compile scripts/analyze_traces.py` | Successful |

The production build retains the existing non-failing Vite chunk-size warning. The full Python suite retains one existing Starlette/httpx deprecation warning. No commit, staging, tag, push, or publication was performed.

Independent Task 6 review found and test-first fixed one metric-key defect: `call_id` reuse across batches was initially undercounted. Superseded-call identity is now `(batch_id, call_id)`, while repeated IDs inside the same batch remain idempotent. Final re-review approved the analyzer and confirmed that Task 6 did not alter the Task 5 runtime/authority files.

## External validation boundary

The configured real Olist initial dashboard smoke test passed. No credentialed real-Qwen voice pilot was run in this task; continuous speech behavior, provider control compatibility, microphone/speaker interaction, and user-study outcomes remain unverified. Automated tests establish code behavior under deterministic fixtures, not participant benefit or real-provider compatibility. Do not infer study efficacy or counterfactual waiting savings from these tests.
