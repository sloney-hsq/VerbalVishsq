# Dataset-adapted VerbalVis Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans; implement the already-approved TASKS.md work packages without further scope expansion.

**Goal:** Independent runnable VerbalVis with dataset + interface loading, transactional chart tools, actual Qwen transport, preserved frontend, and reproducible tests.

**Architecture:** Eight core backend modules; data-specific code belongs in datasets/<name>/interface.py. One session has one immutable dataset version. Tools mutate private drafts; the session performs synchronous authority + revision validation before installing them.

**Tech Stack:** Python, DuckDB, FastAPI, websockets, jsonschema, Vue, Vega-Lite.

**Spec:** DESIGN_ZH.md (corrected dataset-interface scope) and TASKS.md approved by the user's instruction to complete the code.

## Global constraints

- Work only in this repository; archived source/data remain unchanged. No push/publish.
- Preserve frontend visual design; replace domain assumptions and transport bindings only.
- Provider simulation is for tests, never the application backend.
- Synthetic educational data is labelled, not presented as a real study.
- Explicit Python interface paths are trusted local configuration, not user/model-provided code.

## Integration interfaces

`analytics.load_dataset(interface_path: Path, config: dict) -> DatasetAdapter`. Adapter exposes `description: dict`, `definitions: list[dict]`, `execute(name, arguments, scope=None) -> dict`, `close()`. Tool definitions use name/description/parameters (JSON Schema), read_only operations. Result requires success, dataset_version; successful tabular results have rows:list[dict], columns:dict[field, metadata], truncated:bool. Metadata type is nominal/ordinal/quantitative/temporal; label/unit optional. A dataset interface exports open_dataset(config), returning describe()/tool_definitions()/execute(name,arguments,scope)/close(). DatasetAdapter validates and normalizes boundary data, schemas and duplicate names.

`dashboard.Dashboard(dataset_id: str, dataset_version: str)` exposes snapshot() -> dict, begin_draft() -> Draft, commit(draft) -> dict, discard(draft), stage_undo(draft). Draft contains document:dict, base_revision:int and dirty:bool; no live aliases. Snapshot includes views, filters, highlighted, highlight_element, dim_others, dashboard_revision, dataset_id, dataset_version. Tools modify only draft.document and set dirty. commit enforces issued-draft ownership and revision; exactly once; unchanged reads don't increase revision. Undo only pops committed history on successful commit.

`tools.Toolbox(dataset, dashboard)` exposes schemas() -> list[dict], execute(name,args,draft) -> dict. Public chart tools: describe_dataset, create_chart, update_chart, delete_chart, set_analysis_filters, highlight_chart, inspect_dashboard, undo_dashboard. Interface tool names may not collide. create_chart args source:{tool,arguments}, chart_type:bar|line|scatter, x,y,series?,title?. update_chart adds view_id and preserves omitted fields. Views expose id,title,chart_type,x_field,y_field,color,data,columns,source,highlighted; frontend consumes columns metadata. Scope changes re-execute sources atomically. Core tool result has success, payload, error?; interface execute results are wrapped in payload.

`response_protocol.ResponseProtocol` owns epoch, response/batch records and lock; `begin_response(base_revision)`, `revise()`, `suspend()/resume()`, `admit(response_id,call_ids)`, `allowed(response_id)`, `authorize_commit(batch_id,current_revision)`, `record_commit(batch_id,revision)`, `finish_batch(batch_id,success)`. Returns immutable IDs/records or explicit errors; all queries validate server-owned records. Session keeps transport aliases only. Provider response creation is manually requested and bound through a FIFO ticket; automatic response creation must be disabled in provider configuration.

`realtime.AnalysisSession(dataset,browser_send,provider_send,condition,trace)` implements accept_text, handle_provider_event, run_batch, close and uses the real protocol/dashboard/toolbox. Socket wrapper runs two receive loops and serializes sends. Browser event format retains old message names; dashboard_commit carries revision and full authoritative snapshot. Audio uses response_id. Model function outputs checked separately before each send and follow-up. Nonempty accepted analytical text revokes previous authority; exact backchannels resume suspended response; explicit stop revokes without new generation. Ambiguous/empty input leaves no indefinite suspension and asks for clarification.

## Review focus

1. Old provider response.created after supersession cannot acquire new authority (session tests).
2. Undo cancelled or conflicted before commit cannot consume history (dashboard tests).
3. Dataset result schema/version drift cannot silently create a wrong chart (adapter/tools tests).
4. Multi-call output partially sent then revoked must not create follow-up (session tests).
5. Metadata for non-Olist dates/units must actually control Vega encoding (frontend tests).

## Task 1 — Dataset boundary and two interfaces

Files: backend/analytics.py; datasets/olist/interface.py; datasets/education/interface.py; datasets/education/data.csv; tests/test_datasets.py.

- [ ] Write failing tests for loading a custom interface, invalid schema/version, real CSV query with two domains, Olist item/order grain.
- [ ] Implement the Integration interfaces exactly. Olist uses repository-local, Git-ignored data paths via configuration, not archived Python imports; education provides its own tool name and schema.
- [ ] Execute actual SQL with bound filter values and validated identifiers; handle NULL and explicit limits.
- [ ] Run Python tests and review changes before integration.

## Task 2 — Dashboard and public tools

Files: backend/dashboard.py; backend/tools.py; tests/test_dashboard_tools.py.

- [ ] Test private mutation, atomic failure, revision conflict, replay rejection and Undo history before implementation.
- [ ] Implement Dashboard and Toolbox contracts, view metadata, dynamic interface tool registration and public tools.
- [ ] Test two dataset interfaces through identical create/update/filter pathways; reject wrong encodings, collisions, invalid args.
- [ ] Run tests and review.

## Task 3 — Protocol, session, trace and prompt

Files: backend/response_protocol.py; backend/realtime.py; backend/trace.py; backend/prompts.py; tests/test_protocol.py; tests/test_session.py.

- [ ] Test revoked/suspended response effects, duplicate calls, unchanged reads, ordered commits and model-output suppression.
- [ ] Implement sync protocol plus explicit session orchestration, bounded retained records, structured trace with configurable sensitive content.
- [ ] Bind provider IDs to requested responses, handle late events, half/full input policies, cancellation and follow-up without treating provider events as authority.
- [ ] Test provider send failures, response errors and in-flight closing; compare using event barriers, not sleeps.

## Task 4 — Preserved frontend and real application entry

Files: frontend (copy original source/config/assets only, then edit); backend/main.py; tests/test_app.py; frontend/tests/generalDataset.test.js.

- [ ] Preserve existing template/style layout; test temporal/nominal/numeric encoding from columns metadata before changing renderer.
- [ ] Wire WebSocket events, input policy, tool lifecycle, revision-gated commits and response-owned audio.
- [ ] Main loads trusted adapter config, serves websocket and frontend build, exposes dataset description, enforces one active session, closes resources.
- [ ] Keep live transport real; missing credentials surface configuration error, not mock conversation.
- [ ] Run pytest, node tests and production build.

## Task 5 — End-to-end verification and handoff

Files: README.md; requirements.txt; .env.example; configs/*.json; TASKS.md; PROGRESS.md.

- [ ] Run real Olist and education interface queries and full tool batches; document expected results and actual results.
- [ ] Run standalone startup, HTTP checks and websocket with transport-only test doubles; no credentials printed or copied.
- [ ] Independent review of state, transport and dataset boundaries; fix material findings.
- [ ] Clearly separate automated completion, build completion, real provider integration and human microphone/UI tests. No research outcome claims.
