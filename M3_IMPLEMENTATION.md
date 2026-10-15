# M3 Research System Implementation Plan

## Goal

Turn the completed analytical backend and visual analytics runtime into a controlled research system for studying in-flight analytical request revision. The implementation keeps the existing response-authority protocol and private-dashboard-draft commit path intact unless a correctness test exposes a defect.

## Invariants

- The runtime study conditions are `turn_taking` and `revision_enabled`.
- Legacy aliases are accepted only at an external ingress and normalized immediately.
- Runtime classification distinguishes only `empty`, `backchannel`, `stop`, and `analytical_request`.
- Goal, Hypothesis, and Scope are post-hoc research codes, never online control labels.
- Committed dashboard state persists; uncommitted effects may be revoked.
- Tool execution success is distinct from dashboard commit status.
- The two study conditions share the same dataset, tools, model, prompt, dashboard, ASR, and TTS.
- Trace data must be sufficient for reproducible timing analysis and must not contain raw audio.
- No Redis, RAG, MCP, multi-agent runtime, general CSV inference, or complex planner is added in M3.

## Delivery sequence

1. Canonical conditions, utterance roles, and condition-level request gating.
2. Request lifecycle, revision chain, and explicit in-flight semantics.
3. Research trace context/events and prompt constraints.
4. Lightweight frontend revision/superseded feedback and dataset-neutral defaults.
5. Separate execution and commit outcomes, plus stale-result race tests.
6. Offline trace analysis, complete regression suite, and M3 report.

## Milestone acceptance

M3 is complete when the same Olist exploration can run in both conditions, an analytical request arriving during an unsettled request is either rejected or admitted according to the condition, late superseded work cannot change the dashboard or model context, all relevant transitions are traceable, and the offline analyzer derives trial metrics from those traces without fabricated timing values.
