# Task 3/5 independent review

Reviewed the current implementation against the approved design, Task 3 brief, and Task 5 brief. This was a read-only production-code review. The known study-panel/layout squeeze was intentionally excluded.

## Findings

### P1 — A page change can still acknowledge the previously rendered page

- `frontend/src/components/ChartSlot.vue:159` schedules a render when the page changes, but `render()` serializes work behind the currently running render (`frontend/src/components/ChartSlot.vue:185-190`).
- The old ticket is invalidated only when the next queued `performRender()` reaches `renderLifecycle.start()` (`frontend/src/components/ChartSlot.vue:193-196`, `220-233`). Merely scheduling the newer outer `renderGeneration` does not invalidate the lifecycle ticket.
- Consequently, if page 0 is awaiting `view.runAsync()` and the participant clicks **Next**, the old `complete()` still sees its ticket as current and emits a page-0 ACK (`frontend/src/chartRenderLifecycle.js:13-26`) before the queued page-1 render starts.
- `frontend/src/dashboardRenderTracker.js:25-30` validates only token/dashboard/view revision, not whether the emitted presentation is still the component's current page, so it forwards that ACK. The backend accepts either valid page index for the expected view (`backend/render_tracker.py:178-195`) and can declare the token complete.

Reproduction: delay the first Vega view's `runAsync()`, change `pageIndex` with **Next**, then resolve the delayed promise before the queued second render begins. A `view.rendered` event for page 0 is sent even though page 1 is now selected. This violates the Task 3 requirement that stale generations not report and that paging prove only the current page; readiness/freeze can advance without proving the page currently selected by the participant.

### P1 — `trial.task_presented` is fire-and-forget and can lose the no-retry exposure record

- Once the task becomes visible, `frontend/src/components/StudyPanel.vue:137-139` sets the component-local `presented` flag before knowing whether the event was transmitted or accepted.
- `frontend/src/components/Dashboard.vue:117` discards the return value from the send path, and `frontend/src/composables/useWebSocket.js:404-409` returns `null` when the socket is not open.
- Neither connection changes nor rejected/conflict receipts reset `presented` or retry the exact original event. Because `taskVisible` remains true, its watcher does not run again.

Reproduction: deliver an exploring `trial.state`, then close the socket before the immediate watcher sends (or make the socket non-OPEN while the task is already painted). The participant sees the title/prompt, `presented` becomes true, but no server event is recorded. The server may then classify the aborted attempt as unexposed and permit a replacement, contrary to the approved no-retry-after-exposure rule. The exposure observation needs a durable receipt-aware pending/retry path (same event ID/payload), or exposure must be recorded server-side before the visible state is released.

### P2 — Successful questionnaire submission never reaches a visible completed state

- The questionnaire remains visible whenever the completed server state still advertises `questionnaire.submit` (`frontend/src/studyProtocol.js:32-35`; `frontend/src/components/StudyPanel.vue:60-75`).
- `submitQuestionnaire()` only emits the event (`frontend/src/components/StudyPanel.vue:154`); no local state consumes an accepted questionnaire receipt to disable/hide the form or show completion.
- The server continues to advertise `questionnaire.submit` for every completed state (`backend/study.py:286-295`), while the store rejects a second submission as `questionnaire_conflict` (`backend/study_store.py:424-436`). The generic receipt error is rendered only inside the answer form (`frontend/src/components/StudyPanel.vue:54-55`), which is absent in completed phase.

Reproduction: submit all four questionnaire answers. The accepted receipt arrives, but the enabled questionnaire remains and the `Trial complete` notice stays hidden. Clicking submit again produces an invisible conflict. Preserve the accepted questionnaire receipt as a local/server status, disable duplicate submission, and expose a clear saved/completed acknowledgement.

## Areas with no additional finding

The current evidence-checkbox mapping correctly converts selected artifact IDs back to strict `{revision, artifact_id}` references before answer save/submit (`frontend/src/studyProtocol.js:37-57`; `frontend/src/components/StudyPanel.vue:151-153`). The normal production entry mounts `Dashboard`, and the study state, frozen snapshot, render envelope, chart ACK forwarding, and formal `assignment_id` WebSocket context are connected through that entry. Backend token/attempt/view/revision checks and empty-dashboard ACK validation are present. No additional P1/P2 was found there from the current code.

## Focused closure review

All three findings are closed in the current shared worktree:

- The page/presentation race is closed by invalidating the lifecycle generation immediately when `ChartSlot.render()` is scheduled (`frontend/src/components/ChartSlot.vue:185-190`), before queued replacement work begins. The old `runAsync()` completion therefore fails the lifecycle current-ticket check. A focused deferred-promise regression covers this path (`frontend/tests/chartRenderLifecycle.test.js:46-58`).
- The no-retry safety boundary no longer depends on the browser observation: server acceptance of `trial.start` atomically sets `task_exposed` before the exploring state containing the task can be sent (`backend/study_store.py:354-361`). Pre-start failure remains replacement-eligible. The UI additionally waits for an available transport before marking its best-effort `trial.task_presented` observation sent (`frontend/src/components/StudyPanel.vue:142-144`; `frontend/src/components/Dashboard.vue:117-120`). This matches the revised A/C start-exposure contract.
- The questionnaire now enters a pending state, consumes accepted/rejected receipts, hides the form and shows the terminal acknowledgement after acceptance, and keeps a visible retry error after rejection (`frontend/src/components/StudyPanel.vue:60-76`, `99-107`, `123-126`, `145-163`). Runtime wraps successful Store receipts in the top-level protocol status `accepted`, so this path matches the real wire contract (`backend/realtime.py:423-429`).

Verification: `npm test -- --run tests/chartRenderLifecycle.test.js tests/studyPanel.test.js tests/studyProtocol.test.js` completed with 125 passing tests and no failures (the repository script expands its full `tests/*.test.js` glob). No residual P1/P2 remains in the three focused fixes.
