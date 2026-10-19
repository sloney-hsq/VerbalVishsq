# Tasks 3 and 5 implementation report

Date: 2026-10-19  
Owner: B, frontend and render proof  
Worktree: `C:\Users\admin\.codex\worktrees\visual-analysis-tools\VerbalVis`  
Branch: `codex/visual-analysis-tools`

## Scope and preservation

- Added the render-proof tracker, browser render lifecycle, study protocol, single-trial panel, and a clearly labelled synthetic study UI preview.
- Integrated only incremental behavior into the already modified 4K `Dashboard.vue` and `ChartSlot.vue`. Existing responsive grid, card, heatmap paging, typography, and workspace structure were retained.
- Did not edit assignment/store/manifest/scripts owned by C or runtime/controller files owned by A. Did not commit, merge, push, or add dependencies.

## Task 3: real render proof

### Server tracker

`backend/render_tracker.py` implements:

- `RenderTracker.register(attempt_id, snapshot, reason)` returning a fresh `{token, dashboard_revision, expected_views, reason}` envelope for every initial, commit, and frozen snapshot.
- `RenderTracker.ack(attempt_id, event)` returning exactly `{accepted, complete, failed, dashboard_revision, error_code}`.
- Read-only `RenderTracker.status(attempt_id, token)` with the same result shape for lifecycle polling.
- Current-token and attempt ownership, exact expected view revision, strict non-boolean numeric fields, safe `client_event_id`, finite browser duration, presentation shape, and whitelisted error-code validation.
- Explicit empty-dashboard completion using `view_id=null`, `view_revision=null`, and `presentation={mode:'empty',page_index:null}` only when no views were registered.
- Idempotent same-ID/same-payload receipts, `client_event_conflict` for changed payload under the same ID, duplicate render ACK handling, terminal failure, and per-view generation ordering so a late lower-generation failure cannot poison a newer success.

### Browser render lifecycle

- `ChartSlot.vue` now starts a render generation for the active token, awaits both Vega embed and `view.runAsync()`, and emits only after the generation is still current.
- New tokens force every mounted current view to render. Component unmount invalidates all outstanding generations.
- Page/mode/width changes invalidate the in-flight lifecycle ticket immediately, before the replacement render reaches the serialized queue, so an older page cannot complete the current token after the participant changes presentation.
- Render failures send a safe `error_code`; exception strings and chart data never enter ACK payloads.
- ACK presentation records the actually rendered paging mode/page. Existing global scales, category order, paging controls, and card layout remain unchanged.
- `Dashboard.vue` forwards only current-token expected view events through `dashboardRenderTracker.js`; empty dashboards send an explicit render ACK without waiting for a component.
- `init`, accepted `dashboard_commit`, and `trial.frozen` attach their render envelopes. Frozen views are installed from the actual nested `trial.frozen.state` snapshot, including the committed-but-not-previously-sent case.

## Task 5: one-trial study UI

- `StudyPanel.vue` covers `preparing`, `ready`, `exploring`, `answering/pending`, `answering/ready`, `completed`, and `aborted` without exposing task text before Start.
- Both assigned policies share the same Dashboard, chart area, microphone, Stop control, answer form, and questionnaire. Policy-specific busy feedback continues to come only from authoritative input policy.
- There is no typed analysis composer, condition switch, second formal task, or participant `trial.finish` control.
- The countdown locally interpolates server `remaining_ms` for display only and never changes phase, submits, or freezes locally.
- `trial.task_presented` is a client observation emitted once after the task becomes visible.
- Freeze pending disables voice/answers and preserves the frozen charts for reading. Answer controls appear only for `phase=answering, freeze_status=ready`.
- Conclusion, exact ready evidence refs, and limitations use the Store contract. `evidence_refs_ready` and submitted refs are exact `{revision, artifact_id}` pairs from the same attempt; no client-generated evidence identity exists.
- Four separate 1–7 questionnaire items use the exact approved wording and `{responses:{continuity,control,effort,waiting_interference}}` wire envelope. The questionnaire remains available after answer completion when `allowed_actions` permits it.
- Questionnaire submission becomes pending immediately; a matching accepted receipt replaces the form with the visible Trial complete acknowledgement, while a rejected/conflict receipt stays visible beside the retryable form.
- Saved state is shown only after a matching accepted `study.receipt` and matching `draft_version`. A local edit immediately makes the form dirty; an older receipt cannot mark newer text saved.
- Disconnect stops transport/audio, retains component-local unsaved answer text, and does not reconnect or restart a formal attempt automatically.
- `trial.task_presented` is not marked sent while transport is unavailable; the connected/send result drives its local observation flag. The server also records task exposure atomically at accepted Start before releasing the visible exploring state.
- During non-exploring phases the study panel occupies an independently scrollable right rail, leaving the analytical dashboard full height. Exploring keeps the same rail above the transcript. Formal study participants cannot collapse the required rail.

## Exact client wire contract

Every message is `{type, client_event_id, ...payload}`. A retry receives the original event object and reuses its ID and exact payload.

- `trial.start {}`
- `trial.task_presented {}`
- `control.stop {}`
- `answer.save {draft_version, conclusion, evidence_refs:[{revision,artifact_id}], limitations}`
- `answer.submit {submission_id, conclusion, evidence_refs:[{revision,artifact_id}], limitations}`
- `questionnaire.submit {responses:{continuity,control,effort,waiting_interference}}`
- `view.rendered` / `view.render_failed` with only `render_token`, `dashboard_revision`, `view_id`, `view_revision`, `render_generation`, browser-local `browser_duration_ms`, `presentation={mode,page_index}`, and for failure a safe `error_code`.

Server receipts are `{type:'study.receipt',client_event_id,event_type,status:'accepted'|'conflict'|'rejected',receipt?,error_code?}` plus independent `trial.state` messages.

## TDD evidence

RED was observed before implementation:

- `tests/test_render_tracker.py`: collection failed because `backend.render_tracker` did not exist.
- Frontend render lifecycle, dashboard tracker, study protocol, and StudyPanel tests failed because their production modules/components did not exist.
- Follow-up negative tests failed before fixes for changed-payload event-ID conflict, malformed container/bool ACK fields, stale-generation failure, server questionnaire envelope, formal lifecycle state projection, nested frozen snapshot, and control.stop payload.

GREEN coverage includes:

- Old token, wrong attempt, future view revision, duplicate ACK, failed token, independent frozen token, explicit empty dashboard, safe malformed input rejection, event-ID idempotency/conflict, and stale generations.
- `runAsync` completion ordering, stale generation/unmount suppression, error-code-only failures, empty set completion, and current-page presentation.
- Hidden pre-start task, no early finish or text composer, identical voice UI, pending freeze, answer-ready form, completed questionnaire, exact evidence refs, receipt-authoritative Saved state, dirty drafts, and disconnected draft preservation.
- Follow-up review regressions cover immediate stale-page invalidation, connected-only task presentation observation, exact selected evidence pair conversion, questionnaire accepted/error receipts, and right-rail chart preservation during answering.

## Synthetic browser fixture

Use the existing Vite visual-check server and open:

`http://127.0.0.1:5180/study-preview.html`

The fixed top banner labels it **Synthetic study UI fixture** and states that no provider, formal assignment, timing authority, or study record is active. The selector covers Ready, Exploring, Freeze pending, Answering, Completed + questionnaire, and Error/aborted. Query form such as `?state=answering` chooses the initial state. It reuses `/__visual-check-data` so real saved chart cards, heatmaps, long labels, paging, and responsive workspace composition can be inspected. Buttons deliberately do not contact a provider or create a trial.

Parent browser verification passed: at 1366×768 the answering rail scrolls independently while charts retain full height; at 1920×1080 all four completed questionnaire items are visible; Ready exposes only Start and no task; real fixture heatmap paging showed page 2 of 4 without moving the chart workspace.

## Verification and limits

- `frontend/npm test`: **125 passed, 0 failed** after the final code change.
- `frontend/npm run build`: **passed**, 664 modules transformed; only the existing Vite large-chunk advisory was emitted.
- `.venv/Scripts/python.exe -m pytest -q tests/test_render_tracker.py`: **7 passed**.
- `git diff --check`: recorded clean in the final handoff after report completion.
- The local default and bundled Node runtimes are Node 24 (`v24.14.0` and `v24.19.0`), outside the repository's declared Node `>=20.19 <21` range. Tests/build were therefore executed successfully on the available but unsupported runtime; Node 20.19 compatibility remains a host-level verification item.
- The parent agent owns actual browser checks at 1920×1080 and 1366×768. The fixture is not evidence of real provider, microphone, server deadline, persistence, or formal study readiness.
