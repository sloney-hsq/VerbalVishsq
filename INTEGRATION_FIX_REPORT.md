# Integration correctness fix report

Scope: `backend/realtime.py`, `backend/tools.py`, `tests/test_session.py`, and
`tests/test_dashboard_tools.py`. No frontend, dataset interface, protocol module,
application entry, or old-project files changed by this fix wave. No commits.

## Changes

- Centralized browser/provider publication. Response authority is checked again
  inside the serialized-send lock immediately before the transport call. A
  suspended response waits, releasing the lock while waiting; a revoked response
  drops its remaining effects. Batch delivery permits are consumed only at this
  eligible send boundary, separately for each browser event and model output.
- Batch execution/publication/follow-up waits distinguish suspension from
  revocation. Follow-up creation occurs only after every model tool output has
  returned successfully. Provider failures never request follow-up. The existing
  synchronous authority/revision/commit critical section remains await-free.
- Playback-stop and tool-execution-finished control events remain deliverable
  after response revocation.
- Final ASR events must identify the outstanding utterance. Older, unknown, and
  replayed finals cannot resolve a newer suspension. Completed/superseded IDs
  retain a bounded 256-entry replay window; evicted unknown finals still fail the
  outstanding-ID check. Missing speech-start IDs are rejected explicitly.
- Only recognized backchannels resume old authority. Empty or failed ASR revokes
  it, drops held analytical effects, resolves waiting tasks, and asks to repeat
  without starting a new analysis.
- Accepted text/ASR continuations recheck their accepted epoch before installing
  a response and recheck response authority before writing the generation request.
  An older coroutine cannot restore its request after a newer accepted input.
- Shared filters validate descriptor resource-field metadata before touching the
  draft: temporal ISO strings, finite quantitative scalars, null/operator rules,
  and conflicting field types. This works without views or dataset-name branches.
  Nominal/ordinal values remain scalar categories rather than being assumed to
  be strings. Trusted interfaces without resource metadata retain scalar/schema
  validation and their existing query-time semantic validation.
- Lifecycle traces now include response start/create/done, revocation, batch
  admission, committed/current/rejected state, response IDs, epoch/base revision,
  and provider aliases where present. Bounded response context preserves identity
  for late provider callbacks after supersession.

## Regression evidence

Before implementation, focused new regressions reproduced 12 failures (41 passes):
browser-publication suspension, stale ASR finals, empty/failed ASR commits,
browser-lock stale sends, and five invalid temporal values. A strengthened event
barrier also reproduced provider-publication suspension: both backchannel
variants failed while revision variants passed. Additional lifecycle and
concurrent-input checks failed before their corresponding fixes.

Event barriers cover browser and provider first-result sends, backchannel resume,
true revision at the same boundaries, provider-output failure, and serialized
lock suspension without premature permit consumption. Coverage also includes
unknown/replayed ASR, bounded retention, successful temporal-filter-then-chart,
descriptor-driven quantitative values, and late-response trace correlation.

Final verification (working directory: repository root):

```powershell
python -m pytest -q --tb=short
```

Actual output: **97 passed, 1 warning in 2.50s**, exit code 0. The warning is
`StarletteDeprecationWarning` from the installed FastAPI/Starlette TestClient's
use of `httpx` (upstream recommends `httpx2`); no failed tests.

## Remaining boundaries

- A transport call already in flight cannot be retracted. Checks prevent newly
  starting stale sends, not delivery of bytes already handed to a transport.
- An already committed dashboard remains committed if intent changes during
  publication; remaining stale publication and follow-up are suppressed.
- Failed provider publication is not retried: delivery can be ambiguous, so
  background failure revokes the session and requires recovery/reconnection.
- ASR correlation requires provider item IDs and recognized backchannels use the
  documented deterministic baseline, not a learned intent classifier.
- Trusted interface metadata does not sandbox local Python or validate arbitrary
  domain-specific business semantics. Generic checks cannot infer absent metadata.
- Verification here used deterministic transport doubles and real dataset/tool
  tests, not live provider credentials, microphone, or human UI trials.
