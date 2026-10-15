# Contributing to VerbalVis

VerbalVis is a research system. A change is acceptable only when it preserves both software correctness and experimental comparability.

## Local setup

```powershell
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-deps -e .
python -m pytest tests -q
cd frontend
npm ci
npm test
npm run build
```

The real Olist CSV files and a live Qwen credential are not required for the deterministic test suite. Tests that need the locally configured Olist directory skip when it is absent. Never add credentials, participant traces, generated pilot schedules, raw recordings, or licensed datasets to a pull request.

## Change boundaries

- Dataset-specific fields, metrics, SQL, and domain tools belong under `datasets/<dataset>/` and its config. Do not add dataset-name branches to the runtime or frontend.
- `backend/response_protocol.py` owns authority and commit eligibility. Transport code must not create a second ownership state.
- Tools operate on a private dashboard draft. Only a successful authorized commit can publish a dashboard revision.
- The frontend consumes column metadata; it must not infer Olist semantics from field names.
- `turn_taking` and `revision_enabled` must share model, prompts, tools, data, frontend, voice, and dashboard behavior. A change that affects one condition differently requires an explicit research-design justification.
- Trace schema, event names, outcome semantics, pilot tasks, and counterbalancing are research interfaces. Update their tests and research documentation in the same change.

## Tests and review

Add a regression test before fixing a defect. For a feature, exercise the public contract rather than implementation details. Before requesting review, run the complete Python suite, frontend tests, production build, and the focused tests for the changed subsystem. Report skipped real-data or live-provider checks explicitly; never convert a deterministic test result into a user-study or provider-compatibility claim.

Changes to the formal study version should stop after the experiment freeze except for critical correctness, logging, privacy, or safety fixes. Record which trials may be affected by any post-freeze change.
