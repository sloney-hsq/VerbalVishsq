# Task 4 independent read-only review

Date: 2026-10-19  
Reviewer: B (`render_ui_impl_high`)

Reviewed the current `backend/main.py`, `backend/realtime.py`, `backend/study.py`, and Task 4 tests against the approved Task 4 brief and shared wire/lifecycle constraints. The already-known duplicate Stop/replayed state and initial provenance work was excluded. No production file owned by A was edited.

## New findings sent to A and resolved

### P1 — asynchronous evidence failure is not observed while exploring

`StudyController.poll()` checks `failed_jobs` / `attempt.evidence_failure` only while `preparing` and while frozen readiness is `answering/pending`. An evidence worker can fail after an accepted dashboard commit while the controller remains `exploring`; the 50 ms monitor continues polling, but no branch closes the gate or aborts. Further audio, analysis, and commits can therefore be accepted against a formal attempt whose required evidence persistence has already failed, potentially until the 10-minute deadline.

Required correction: during `exploring`, poll the same store failure state, synchronously close the analysis gate, persist/emit one safe aborted state, and do not roll back the already legal dashboard commit. Add a regression with a commit evidence job that becomes failed after enqueue.

Resolution verified in the shared worktree: `poll()` now checks the asynchronous evidence failure state while exploring, aborts the controller, and closes `check_effect`; `test_async_evidence_failure_aborts_while_still_exploring` covers the transition.

### P1 — direct answer persistence exceptions leave the trial live

For `answer.save` and `answer.submit`, an unexpected Store I/O exception escaped `StudyController.handle_control()`. `AnalysisSession.handle_study_event()` caught it generically and emitted only a rejected `study.receipt`; it did not abort the controller or emit `trial.state` aborted. Thus a real answer persistence failure could leave the participant in an apparently retryable answering UI instead of terminating the formal trial. The answer-timeout path already aborted on persistence error, so direct controls were inconsistent with that lifecycle.

Required correction: keep expected `StudyStoreError` validation/conflict outcomes as rejected receipts, but treat unexpected answer persistence exceptions as terminal, call the controller's safe abort path, and emit the resulting aborted state. Questionnaire persistence is intentionally different: the approved absorbing completed state and optional questionnaire rule require a visible rejected receipt and retry opportunity without reversing the completed answer.

Resolution verified in the shared worktree: direct answer persistence failures now raise a safe `StudyError` carrying the aborted state, and the realtime layer emits both the rejected receipt and state. `test_answer_persistence_failure_aborts_with_safe_state` covers it. Questionnaire persistence stays completed with `questionnaire_persist_failed`, as required.

## Areas checked without a new finding

- Assignment condition authority and browser text rejection versus ASR reuse.
- Synchronous deadline checks around audio dispatch, ASR return, commit CAS, and committed-but-unsent frozen snapshots.
- Turn-taking floor across tool follow-up generation, final playback, and stale playback ACKs.
- Initial/frozen render plus evidence readiness gates and the shared 15-second timeout.
- Exact study receipt and render ACK routing, single-task task visibility, Stop cancellation, and formal provenance admission.

The two findings were messaged directly to A, corrected, and re-inspected before final verification. No open P1/P2 remains from this review.
