# Task 2 — Dashboard and public tools

Implemented only `backend/dashboard.py`, `backend/tools.py`, and `tests/test_dashboard_tools.py`, plus this report. No commits. Existing changes elsewhere were left untouched.

## Contracts delivered

- `Dashboard(dataset_id, dataset_version)`: detached snapshots/drafts, server-issued draft identity, immutable recorded base revision, compare-and-swap commit, once-only consumption, idempotent discard after success or cancellation. Read-only and no-op commits do not increase the revision.
- Undo copies the prior committed state into a draft; history is popped only by a successful matching commit. Cancelled/conflicted Undo leaves history intact. Undo cannot be mixed with another mutation in its draft. Later committed changes remain undoable in order.
- `Toolbox(dataset, dashboard).schemas()` returns detached flat `{name, description, parameters}` definitions. Dataset definitions dynamically register and must be read-only without collisions. Dataset/dashboard identity and version must match.
- `execute(name, args, draft)` validates arguments and draft ownership, returns `{success, payload, error?}`, restores document and dirty flag after failed calls, and leaves live dashboard mutation exclusively to commit. Failed domain calls retain the adapter's full result in `payload`.
- Charts accept only registered dataset sources, never SQL or public-tool recursion. Requested x/y/series columns must exist. Bar x is nominal/ordinal/temporal; line x is temporal/ordinal/quantitative; scatter x is quantitative. All y columns are quantitative; series is nominal/ordinal.
- Views preserve `id`, `title`, `chart_type`, `x_field`, `y_field`, `color`, `data`, `source`, `highlighted`, and add `columns` metadata and `truncated`.
- Shared scopes are filter lists. Fields/operators/scalar values are checked before rerunning sources, including on empty dashboards. All source candidates are computed before installing filtered views. A later source schema change rolls back the whole filter call.

## Integration notes and rulings

- `highlight_chart` arguments: `{view_id: string|null, element?: object|null, dim_others?: boolean}`. Null view ID clears highlighting. `highlighted` is a list of IDs; `highlight_element` is the supplied object or null.
- Create/update payloads are the view. Filter/highlight/inspect/Undo payloads are snapshot-shaped draft documents. Describe payload is the dataset descriptor, whose version key remains `version`. Dataset query result version remains `dataset_version`.
- Omitted update fields are preserved; explicit `series: null` clears color encoding. An update re-executes its source. This ensures metadata and data remain synchronized but performs a query even for title-only changes.
- Filter validation uses descriptor `filters.fields` and `filters.operators`; arbitrary third-party domain-specific value semantics are still owned by the registered interface. The two supplied adapters accept scalar filter values and supported fields/operators.
- Batch-wide atomicity, authority and standalone-Undo batch admission remain the session's responsibility. A failed tool call restores that call's prior draft state; it does not erase earlier successful calls in the same draft.
- This task followed the already-approved implementation plan and assigned ownership boundaries; it did not create a new worktree, commit, or dispatch agents. Final whole-project integration/review remains with the coordinating agent.

## Verification

Validation used Python 3.11 from a local virtual environment; commands ran from the standalone repository root.

1. Initial test-first run: Dashboard/Toolbox absence produced the expected missing-implementation assertion; no implementation files existed yet.
2. Initial implementation: `-m pytest tests/test_dashboard_tools.py -q` — **23 passed**.
3. Added failure-wrapper regression: **1 failed, 27 passed**, because failed domain query payload was incorrectly null. Corrected wrapper, reran — **28 passed**.
4. Latest `-m pytest tests -q` — **53 passed**, one existing Starlette/httpx deprecation warning.
5. An earlier broad workspace run is archived outside this repository because it included unrelated projects and is not release evidence for this codebase.
6. `git diff --check` exited zero; existing line-ending notices in unrelated workspace material are not part of this report.

Coverage includes actual education and Olist adapters through the same create/update/filter pathway, detached payloads and snapshots, private mutation, revision conflicts, replay/foreign/copied/discarded draft rejection, no-op/read-only revisions, cancellation-safe Undo, standalone Undo, per-call rollback, schema/name collision errors, semantic chart validation, null aggregates, temporal metadata, and later-source schema drift.
