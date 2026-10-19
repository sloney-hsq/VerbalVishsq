# Owner C Tasks 1, 2, 6 implementation report

Date: 2026-10-19  
Worktree: `C:/Users/admin/.codex/worktrees/visual-analysis-tools/VerbalVis`  
Branch: `codex/visual-analysis-tools`  
Status: implemented locally; no commit, merge, or push.

## Implemented scope

- Task 1: versioned between-subject manifest, deterministic task-block allocation, validated trusted-directory assignment loading, schedule CLI, study output ignores, and task-pool 2.0 test correction. The existing six-workflow real-toolbox replay remains unchanged.
- Task 2: stdlib SQLite attempt/journal/idempotency/answer/questionnaire index plus a separate in-memory bounded immutable evidence queue. Artifact serialization and SQLite registration happen only in the study-owned asynchronous flush worker; files use same-directory temporary files, `fsync`, atomic replace, SHA-256 registration, per-attempt 50 MiB accounting, and fail-closed status.
- Task 6: assignment-denominator audit and separate whitelisted technical, blinded-ratings, and consent-aware process exports. No exporter copies SQLite tables, Trace JSONL, client event receipts, raw audio, or unrestricted logs.

## Public configuration and assignment contract

Manifest: `experiments/olist_voice_policy_between_v1.json`.

- `schema_version=1`, `design=between_subjects`, `study_version=1.0`.
- Conditions: `revision_enabled`, `turn_taking`.
- Limits: exploration 600 s, answer 180 s, freeze readiness 15 s, evidence 50 MiB per attempt, answer text 8000 characters.
- Consent: `transcript` optional; `analysis_evidence` and `final_answer` required.
- The two title/prompt pairs are byte-for-byte copies of task pool 2.0. Each prompt hash covers only prompt UTF-8 bytes. The source pool byte hash is checked by the CLI. Manifest hashing excludes only its own top-level hash fields.

Schedule assignment identity fields are exactly:

`assignment_id, participant_id, trial_id, task_id, condition, dataset_id, study_id, study_version, manifest_sha256, is_practice=false`.

`attempt_id` and `session_id` are never scheduled. `load_assignment(...)` returns those identity fields plus server-resolved `task={task_id,title,prompt,prompt_sha256}` from the validated schedule catalog. The loader revalidates 12 unique participants/trials/assignments, 6 per condition, 3 per task-condition cell, all top-level identities, hashes, and the controlled directory scan; it never joins a client value into a path.

## Public Python APIs

`backend.study_manifest`:

- `validate_manifest(payload: dict) -> dict`
- `prepare_cohort(manifest: dict, participant_ids: list[str], seed: int = 20261019) -> dict`
- `load_assignment(schedule_dir: Path, assignment_id: str, dataset_id: str) -> dict`

`backend.study_store`:

- `StudyStore(root: Path)`
- `begin_attempt(assignment, session_id, consent, provenance) -> {attempt_id,phase,session_id,assignment_id}`
- `apply_event(attempt_id, client_event_id, event_type, payload) -> receipt`
- `append_event(attempt_id, event, metadata, now_ns) -> None`
- `enqueue_evidence(attempt_id, snapshot, provenance) -> job_id` (synchronous deep serialization and bounded memory enqueue only; no file/SQLite I/O)
- `await flush_evidence(attempt_id) -> None` (concurrent flushes claim each job once and run file/SQLite work in `asyncio.to_thread`)
- `evidence_ready(attempt_id, revision) -> bool`
- `get_evidence_status(attempt_id) -> {ready_revisions,pending_jobs,failed_jobs,bytes_used,limit_bytes,error_code}`
- `get_evidence_refs(attempt_id) -> [{revision,artifact_id}]`
- `get_attempt`, `list_attempts`, `list_events`, `list_answers`, `list_questionnaires`, `list_evidence`
- `recover_incomplete() -> list[attempt_id]`
- Errors are `StudyStoreError` with stable `.code`.

`begin_attempt` consent is exactly three booleans; evidence/final-answer must be true. Provenance is exactly `git_commit, git_dirty, model, prompt_sha256, tool_schema_sha256, dataset_version, initial_dashboard_sha256`. Accepting `trial.start` atomically marks the task exposed because the returned exploring state contains the trusted task; `trial.task_presented` remains a browser observation but is not the sole retry barrier. Any historical started/exposed or completed attempt blocks a new attempt for that assignment. A pre-start aborted or unexposed nonterminal attempt remains eligible for replacement; an unexposed nonterminal attempt is preserved as aborted before that replacement is created.

`apply_event` exact payloads:

- `trial.ready {}`
- `trial.start {}`
- `trial.task_presented {}`
- `trial.freeze {reason,frozen_revision,last_rendered_revision}` -> `phase=answering, freeze_status=pending`
- server-only `trial.answering {}` -> `freeze_status=ready`
- `answer.save {draft_version,conclusion,evidence_refs,limitations}`
- `answer.submit {submission_id,conclusion,evidence_refs,limitations}`
- `answer.timeout {}`
- `questionnaire.submit {responses:{continuity,control,effort,waiting_interference}}`
- `trial.abort {reason_code}`

Message idempotency uses `(attempt_id, client_event_id)` plus a canonical event/payload hash. Submission business idempotency uses `(attempt_id, submission_id)` plus answer content hash. Same content returns the original receipt; changed content conflicts. Answer refs are exact `{revision:int>=0,artifact_id:safe-token}` values and must be ready, same-attempt, same-revision artifacts. Answer save/submit/timeout are rejected until freeze readiness is `ready`. Questionnaire values are four exact integers from 1 through 7.

Runtime journal names aligned with Owner A are `trial.ready`, `trial.started`, `trial.commit_registered`, `trial.frozen`, `trial.answering_ready`, `trial.aborted`, `control.stop`, and `request.accepted`, with exact metadata whitelists. Optional transcript text is discarded before persistence when transcript consent is false. Existing bounded future diagnostics remain `response.stopped`, `deadline.reached`, `render.status`, `evidence.status`, and `persistence.failure`.

`scripts.audit_study.audit_assignments(schedule, attempts, trace_summaries) -> dict` returns `planned, started, completed, aborted, missing, practice_attempts, formal_attempts, assignments, diagnostics`. Assignment is the only denominator; retries and practice never add samples. Every planned assignment with no observed attempt has a `missing_assignment` diagnostic, so `--strict` rejects an empty-but-valid 12-person collection database without altering the 12-assignment denominator. Attempt order uses `created_ns`, and analyzer diagnostics/missing trace/session/context mismatches are retained.

`scripts.export_study.export_study(study_root, output_dir, *, package) -> dict` accepts only `technical`, `ratings`, or `process`. It rejects a missing database and any existing output directory. Ratings omit condition, participant/session identity, transcript, latency, and timestamps; evidence files are ready/same-attempt/hash/path checked. Process includes transcript only when authorized. Export construction uses a sibling staging directory and atomic directory replace.

## CLI

```powershell
.\.venv\Scripts\python.exe scripts\prepare_study.py --manifest experiments\olist_voice_policy_between_v1.json --participants 12 --seed 20261019 --output study_schedules\cohort.json
.\.venv\Scripts\python.exe scripts\audit_study.py --schedule study_schedules\cohort.json --study-data study_data\cohort --traces traces --output study_exports\audit.json --strict
.\.venv\Scripts\python.exe scripts\export_study.py --study-data study_data\cohort --output study_exports\technical --package technical
.\.venv\Scripts\python.exe scripts\export_study.py --study-data study_data\cohort --output study_exports\ratings --package ratings
.\.venv\Scripts\python.exe scripts\export_study.py --study-data study_data\cohort --output study_exports\process --package process
```

All three scripts run directly from a clean repository cwd. Prepare/export refuse overwrite. Audit/export reject nonexistent or mistyped study databases without creating an empty database.

## TDD and verification evidence

RED was observed before implementation:

- schedule: import failed with `ModuleNotFoundError: backend.study_manifest`;
- store: import failed with `ModuleNotFoundError: backend.study_store`;
- audit/export: imports failed because both scripts were absent;
- subsequent focused RED cases caught rehashed-unbalanced schedule acceptance, exposed/completed assignment restart, enqueue SQLite I/O, unrestricted evidence fields, missing-database silent creation, random-ID retry ordering, runtime journal mismatch, concurrent double flush, and `server:<uuid>` internal-ID rejection.
- final review RED cases caught strict audit exit 0 for all 12 missing assignments (2 failures before the fix) and the gap between accepted `trial.start` and the later best-effort task-presented observation (1 failure before the fix).

GREEN commands/outcomes:

- Owner C + Trace/Pilot regressions: 95 passed.
- Owner C + Owner A/B study integration set: 121 passed, one existing Starlette/httpx deprecation warning.
- Final complete Python suite: `428 passed, 1 warning in 28.79s` using `.\.venv\Scripts\python.exe -m pytest tests -q`.
- `git diff --check`: clean.
- Post-review C-focused results: `tests/test_study_audit.py` 7 passed; `tests/test_study_store.py` 13 passed. After Owner A resolved its concurrent controller-idempotency assertion, the seven-file C/A integration rerun completed with `63 passed, 1 warning in 4.74s`.

## Pre-review findings resolved

- Load-time schedule validation now rechecks the full 12/6/3 design and top-level identities, not merely generator output.
- Evidence enqueue is disk-free, bounded, deeply serialized, and atomically flushed by the independent worker; concurrent flush calls cannot process a job twice.
- Completed and any previously exposed assignment are permanently ineligible for restart, including after disconnect/recovery.
- Evidence accepts only known Dashboard and view fields, validates source shape/data/columns, and recursively rejects transcript/audio/credentials/secrets/path keys.
- Audit/export do not create empty study databases on input errors.
- Audit preserves analyzer diagnostics, reports missing traces, and orders attempts by creation time.
- Store token validation now accepts Owner A's `server:<uuid>` internal event IDs; a real `StudyController + StudyStore` integration test covers start/journal/transcript behavior.
- Missing assignments now emit assignment-specific diagnostics, including the all-unstarted cohort, while `planned/started/missing` remain assignment-based.
- The durable no-retry boundary is the atomic server acceptance of `trial.start`; loss of the browser-only `trial.task_presented` observation can no longer make a disclosed task replacement-eligible.

## Known external gaps

- No claim is made about live provider compatibility, microphone/speaker behavior, actual browser rendering, ethics approval, human scoring, or participant outcomes. Those remain the main-agent preflight/freeze responsibilities.
- The only full-suite warning is the pre-existing Starlette `TestClient` / httpx deprecation warning.
