# Task 4 — runtime/lifecycle implementation report

## Outcome and owned files

Implemented the server-authoritative formal-study runtime while preserving the legacy `AnalysisSession` constructor and Trace v2 path.

- `backend/study.py` — `StudyController`, lifecycle/timing gates, idempotent control receipts, immutable freeze/readiness and answer timeout.
- `backend/realtime.py` — formal voice-only input, deadline checks at authorization and actual send, render/evidence wiring, Stop behavior, request journaling.
- `backend/main.py` — trusted assignment loading, formal/preflight config, provenance enforcement, durable Store/RenderTracker/controller WebSocket lifecycle.
- `tests/test_study_lifecycle.py` — controller and real Store/RenderTracker integration regressions.
- `tests/test_study_runtime.py` — response-protocol timing, send-lock, replay, turn-taking, and real WebSocket integration regressions.

No dependency was added. No commit, merge, or push was made.

## TDD evidence

RED was observed before implementation for the new lifecycle/runtime modules (missing `backend.study` and missing study-aware session behavior). Subsequent focused RED/GREEN cycles covered:

- startup requires both a real render ACK and durable initial evidence before `trial.start`;
- deadline boundary wins over readiness at exactly 15 seconds;
- a pre-deadline authorized commit remains valid when the clock crosses the deadline immediately afterward;
- freeze captures an immutable committed-but-unsent snapshot/token before waiting on a busy browser/provider lock;
- answer save/submit synchronously enforce the 180-second deadline;
- replaying a successful Start returns the original receipt plus the current answering/completed state without resetting either deadline;
- replaying an old Stop has no action and cannot cancel a subsequently accepted analytical request;
- accepting Start atomically records task exposure before the first task-bearing state can be emitted.

Final verification after all shared cross-review fixes:

- Required target set: `124 passed, 1 warning in 2.31s`.
- Full Python suite: `439 passed, 1 warning in 31.61s`.
- The sole warning is the existing Starlette `httpx` TestClient deprecation; there were no failures or errors.

## Runtime invariants

- Formal identity and condition come only from a validated server schedule. The WebSocket accepts only `assignment_id`; condition, participant, trial, task, paths, and snapshots are rejected as client authority.
- Formal browser `text` is rejected; provider ASR remains the analytical-input path. Both study conditions therefore remain voice conditions.
- Phases are `preparing -> ready -> exploring -> answering -> completed`, with any nonterminal phase able to become `aborted`. There is no separate freezing phase.
- `trial.start` begins the fixed 600-second exploration deadline. Task exposure is persisted in the same Store transaction before the task-bearing state is emitted.
- `check_effect` is synchronous/read-only. Input, commit, and analysis output are checked at entry and again after the corresponding transport lock. Commit authorization and Dashboard commit stay in the ResponseProtocol guard with no await or disk I/O.
- A legal commit is captured for evidence using its authorization timestamp. Evidence enqueue failure closes the gate without rolling back the already committed Dashboard.
- Deadline closure synchronously revokes response authority, snapshots/registers/enqueues the freeze before cancellation or browser I/O, and gives the frozen snapshot a new render token even if its revision was committed but not yet sent.
- Frozen render and evidence share one 15-second total readiness deadline. Only both-ready transitions `freeze_status` from `pending` to `ready` and starts the fixed 180-second answer deadline.
- Answer timeout persists the latest confirmed draft as `partial`, or an empty answer as `empty`; both are completed study outcomes, not transport failures.
- `control.stop` revokes the current response and stops playback in both conditions without creating analysis. A replay returns the original receipt but no repeated Stop action.
- Exploring polls abort immediately if an asynchronous evidence writer reports failure. Unexpected answer save/submit persistence failures emit a rejected receipt plus an aborted state. Questionnaire persistence failure reports an error but does not reverse a completed answer, per the terminal-state rule.
- Accepted analytical requests append `request.accepted` with request ID, classification, and transcript. `StudyStore` omits transcript when transcript consent is false; Trace v2 retains its existing consent/redaction behavior.

## Formal launch configuration

Use a trusted config outside the tracked checkout (or in an ignored operator-only location) so inserting the expected commit cannot itself dirty/change the frozen commit. Example:

```json
{
  "interface": "datasets/olist_interface.py",
  "dataset": {"data_dir": "C:/trusted/olist-data"},
  "trace_dir": "C:/trusted/voice-study/traces",
  "initial_dashboard": [],
  "study": {
    "enabled": true,
    "mode": "formal",
    "schedule_dir": "C:/trusted/voice-study/schedules",
    "data_dir": "C:/trusted/voice-study/formal-data",
    "consent": {
      "transcript": false,
      "analysis_evidence": true,
      "final_answer": true
    },
    "expected_provenance": {
      "git_commit": "<40-hex commit>",
      "git_dirty": false,
      "model": "qwen3.5-omni-plus-realtime",
      "prompt_sha256": "<sha256>",
      "tool_schema_sha256": "<sha256>",
      "dataset_version": "<configured dataset version>",
      "initial_dashboard_sha256": "<sha256>"
    }
  }
}
```

`initial_dashboard_sha256` is computed after the constructor synchronously materializes all configured initial views, and before provider configuration; it is the actual committed initial Dashboard snapshot, not an empty/default config hash. `prompt_sha256` is over the exact instructions built from dataset description, tool schemas, and that same snapshot. Formal startup rejects a dirty checkout or any mismatch in commit, model, prompt, tool schema, dataset version, or initial Dashboard.

Operator sequence:

1. Prepare/validate the fixed schedule and nine Olist CSVs. Keep schedule, data, Trace, and StudyStore roots access-controlled.
2. On the intended clean commit and exact environment, run one `mode: "preflight"` connection using **separate throwaway schedule, study-data, and trace roots**. Read the created attempt's `provenance` via `StudyStore(<preflight-data>).list_attempts()` and copy the seven exact fields into the external formal config.
3. Delete or retain the isolated preflight roots according to the dry-run policy; never point formal audit/export at them. Preflight does not change `is_practice`: fixed schedule assignments remain `is_practice:false`, so directory isolation is mandatory.
4. Confirm `git status --porcelain --untracked-files=all` is empty and `git rev-parse HEAD` equals `expected_provenance.git_commit`.
5. Obtain participant consent manually before opening the assignment. Set the config consent booleans to that recorded decision; there is no automatic consent inference.
6. Set `VERBALVIS_CONFIG` to the trusted JSON, provide `DASHSCOPE_API_KEY` through the process environment, and launch exactly one worker:

```powershell
$env:VERBALVIS_CONFIG = 'C:\trusted\voice-study\formal.json'
$env:DASHSCOPE_API_KEY = '<operator-provided secret>'
$env:QWEN_REALTIME_MODEL = 'qwen3.5-omni-plus-realtime'
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --workers 1
```

7. Connect with `/ws?assignment_id=<server-issued-assignment-id>`. Do not add condition or participant fields.

The configuration deliberately fails closed if a `study` object is present with `enabled` other than literal `true`. Omit `study` entirely for the legacy non-study entry.

## Exact study wire

Client to server (all IDs are stable safe tokens; a retry reuses the original complete event unchanged):

```text
{"type":"trial.start","client_event_id":"..."}
{"type":"trial.task_presented","client_event_id":"..."}
{"type":"control.stop","client_event_id":"..."}
{"type":"answer.save","client_event_id":"...","draft_version":1,"conclusion":"...","evidence_refs":[{"revision":1,"artifact_id":"..."}],"limitations":"..."}
{"type":"answer.submit","client_event_id":"...","submission_id":"...","conclusion":"...","evidence_refs":[{"revision":1,"artifact_id":"..."}],"limitations":"..."}
{"type":"questionnaire.submit","client_event_id":"...","responses":{"continuity":1,"control":1,"effort":1,"waiting_interference":1}}
{"type":"view.rendered|view.render_failed","client_event_id":"...","render_token":"...","dashboard_revision":1,"view_id":"...|null","view_revision":1,"render_generation":1,"browser_duration_ms":12,"presentation":{"mode":"...","page_index":null},"error_code":"... only for failure"}
```

Server to client study messages:

```text
{"type":"study.receipt","client_event_id":"...","event_type":"...","status":"accepted|conflict|rejected","receipt":{...},"error_code":"... optional","seq":N}
{"type":"trial.state","phase":"preparing|ready|exploring|answering|completed|aborted","freeze_status":"pending|ready|failed|null","remaining_ms":N|null,"answer_status":"submitted|partial|empty|null","evidence_refs_ready":[{"revision":1,"artifact_id":"..."}],"allowed_actions":[...],"task":{... only after Start},"seq":N}
{"type":"trial.frozen","state":{... immutable full Dashboard snapshot},"dashboard_revision":N,"frozen_committed_revision":N,"last_rendered_revision":N|null,"render":{...},"freeze_status":"pending","seq":N}
```

`init` also carries the initial render envelope. A task is never present in preparing/ready state; the Start transaction marks exposure before the server sends the first exploring state containing `task`.

## Gaps and non-claims

- No live provider credential was available in this process, so this report does not claim a real DashScope/provider pass or capture raw audio.
- Automated tests use a provider/WebSocket contract fixture; an operator still must do the documented clean-checkout preflight and supervised participant launch.
- Preflight is a provenance collection mode, not a practice-attempt flag. Its roots must remain isolated from formal collection and audit.
- The formal config intentionally has no automatic provenance writer because its source must be an operator-controlled external/ignored file after the target commit is clean.

## Read-only review of C-owned manifest/store/audit/export

Shared A/C contracts align: server IDs are accepted, lifecycle/request journals are whitelisted, transcript is consent-filtered, evidence refs are ready and attempt-local, artifacts are hash/path checked on export, and terminal answers survive disconnect. The audit missing-assignment strict-mode issue found during review and the Start/exposure atomicity issue are fixed in C ownership and covered by the final suite; no C-owned file was edited here.
