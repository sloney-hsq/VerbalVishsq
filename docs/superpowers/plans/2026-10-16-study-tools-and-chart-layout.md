# Study Tools and Chart Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement your assigned tasks; the parent coordinates using superpowers:subagent-driven-development. Steps use checkbox syntax.

**Goal:** Deliver the approved five analysis tools, six-task replay, and readable responsive chart layouts.

**Architecture:** Keep the registered dataset adapter and transactional dashboard. Shared predicates and measure semantics feed all queries; a pure frontend presentation layer controls card sizing and heatmap pages without mutating analytical state.

**Tech Stack:** Existing Python/DuckDB/FastAPI, Vue/Vega-Lite, pytest and Node test runner; no new production dependency.

**Spec:** `docs/superpowers/specs/2026-10-16-study-tools-and-chart-layout-design.md` (user approved and requested execution on 2026-10-16).

## Global Constraints

- Work only at `C:/Users/admin/.codex/worktrees/visual-analysis-tools/VerbalVis`, branch `codex/visual-analysis-tools`; implementation base `98db3e9`.
- Use the two existing GPT-5.6-Sol agents. Backend owns `backend/`, `datasets/`, Python tests, `scripts/check_study_tools.py`, and the new task pool. Frontend owns `frontend/`. Parent owns documentation and final verification.
- Do not spawn helpers. Do not edit raw CSVs, original checkout, credentials, shared node_modules, or old pilot schedules. No merge/push.
- Preserve legacy APIs, Education, atomic drafts, revision rejection, and voice protocol. No intent encoder, arbitrary SQL/formulas, regression or causal claims.
- Use apply_patch for edits and TDD; focused tests while iterating, full owned suite before delivery. Stage only owned paths; ask parent for a commit slot to avoid concurrent index changes.
- Exactly follow the approved spec for parameter names, ID restrictions, grains, boundaries, limits, missing values, layout sizes and semantic warnings. Report implementation deviations rather than silently dropping requirements.

## Review Focus

- OR with an order-only branch and an order without items must not disappear through an inner join; same-item AND must not combine different items (Task 1).
- Updating one dynamic measure must not rename chart columns, silently lose filters, or discard a fixed quantile threshold (Tasks 1–2).
- A missing period bucket is not a measured zero and record presence is not proof of data completeness (Task 3).
- Paging must group all cells of each category, keep global color domains, preserve off-page selection and never change dashboard revisions (Task 4).
- Real chart container width includes the conversation sidebar; rapid resize/redraw and unmount must not leak stale Vega instances (Task 4).

## Task 1: Shared predicate and measure contracts

**Files:** Modify `datasets/olist/query_common.py`, `schema.py`, `metrics.py`, `queries.py`, `interface.py`; create `datasets/olist/measure_queries.py` and `predicate_plan.py` for focused logic. Modify `backend/filter_contract.py`, `chart_patch.py`, `tools.py`, `analytics.py` as required by generic contracts. Add `tests/test_study_predicates.py`, `tests/test_study_measures.py`; extend existing tool tests.

**Interfaces:** Public queries preserve `execute(name, arguments, scope)`. New measure definitions and OR/quantile filter shapes are exactly those in the spec. Query helpers remain private to the adapter; expose normalized output `rows/columns/result_kind/metadata` through its existing interface. New metadata must include stable measure definitions and row-aligned valid denominators.

- [ ] Write failing tests with real synthetic adapter fixtures: mean([1,3,9])=13/3, median=3, q=.9 gives 7.8; threshold <=3 gives 2/3; registered total ratio uses matched eligible rows. Test no-data/null, duplicate IDs, invalid unit, four-total-measure cap and SQL-looking values as data only.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_study_predicates.py tests/test_study_measures.py -q`; record RED before implementation.
- [ ] Implement bounded AND/OR validation and one shared predicate plan. Assert order-only OR admits an order with no item; an order whose different items separately satisfy two AND leaves must not match. Keep default delivered explicit and reject status in OR.
- [ ] Implement registered measures and ID-based measure changes; old fixed metrics remain compatible. Exercise dynamic IDs in having/sort/top_k, and source-switch scope preservation with OR groups. Make required-argument checks schema-driven rather than hardcoded metrics.
- [ ] Implement complete-base-population quantile resolution and snapshot materialization. Test independent simultaneous rules, no group/sample influence, EMPTY_REFERENCE_POPULATION, linked recomputation and fixed snapshot boundaries. Reject shared/OR/segment-local quantile rules explicitly.
- [ ] Run focused plus existing analysis/filter/chart tests; commit only owned paths after parent grants commit slot. Report precise commands, RED/GREEN, metadata shapes and concerns.

## Task 2: Segment, distribution and relationship extensions

**Files:** Modify `datasets/olist/interface.py`, `distributions.py`, `relationships.py`, `measure_queries.py`; extend result validation in `backend/analytics.py` and chart validation in existing backend modules; add `tests/test_study_comparisons.py`, `tests/test_study_distributions.py`, `tests/test_study_relationships.py`.

**Interfaces:** Consume Task 1 predicates/measures and stable IDs. Preserve wide segment rows; derived columns use `id__difference`, `id__relative_difference`, `id__percentage_point_difference`. Produce new result kinds `quantiles` and `relationship_summary`; declare quantitative columns, source semantics, units `ratio`, `percentage_points`, `correlation`, and validity metadata.

- [ ] Write failing tests: .15 versus .10 yields .05 difference, .5 relative, 5 percentage points; zero/null references yield null relative; missing breakdown references remain null. Group-overlap metadata and valid-count denominator survive comparisons.
- [ ] Write failing quantile output and Pearson/Spearman tests with ties, constant arrays, invalid pairs and grouped overlap. Assert correlation values do not depend on display sample seed or budget.
- [ ] Run focused tests and capture RED; implement spec-defined comparison and quantiles, using continuous full-data quantiles. Add only the approved complete categorical compositions; overlapping order-category breakdowns remain non-normalizable.
- [ ] Implement optional complete-data correlations and summary representation. Test summary rejects sampling/bins, n<2 and zero variance return reasons, and overall statistics de-duplicate observations across overlapping groups.
- [ ] Run tests for all touched interfaces plus Education and legacy tools; commit after coordination. Send frontend the final metadata keys, without changing its files.

## Task 3: Period comparisons and six-task real-data replay

**Files:** Create `datasets/olist/periods.py`, `tests/test_study_periods.py`, `scripts/check_study_tools.py`, `tests/test_study_flows.py`, `experiments/olist_study_task_pool.json`; modify `datasets/olist/interface.py` and relevant result/chart validation.

**Interfaces:** Register `compare_periods` exactly as spec. Summary returns wide rows by period and groups; series additionally emits bucket_index/start/end/present. New result_kind=`periods`; comparison formulas reuse Task 2. Export replay views as a JSON mapping accepted by frontend render scripts.

- [ ] Write failing summary/series fixtures for day, Monday week, month, explicit unequal summary windows, aligned equal-count series, absent buckets, date-range clipping, zero baseline and P90 measures. Assert absent bucket measures are null, not zero; record_count remains 0; no metadata calls presence proof of complete collection.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_study_periods.py -q` and capture RED; implement one period spine plus shared query path, [start,end) boundaries, nonoverlapping windows, reference pairing and coverage warnings.
- [ ] Create the six-task pool using the exact approved IDs/prompts. Do not change the existing pilot manifest or allocation scripts. Keep tasks open-ended; replay call sequences are researcher-only.
- [ ] Implement `run_workflows(data_dir, *, export=None)` in `scripts/check_study_tools.py`; CLI accepts `--data-dir` and `--export`. Exercise all six tasks through real Toolbox drafts, with stable-ID updates, OR, quantile exclusion, baseline fork, period comparison and undo. No model/provider calls.
- [ ] Test synthetic expected values/state invariants; run real Olist replay and export representative views under this plan's ignored artifact directory. Record operation timings and eligible/valid counts, not fabricated study outcomes.
- [ ] Run full Python suite and legacy smoke, then commit owned paths and write backend report. Any inability to complete a required feature must be raised explicitly.

## Task 4: Responsive chart layout and heatmap browsing

**Files:** Modify `frontend/src/chartLayout.js`, `chartSpecs.js`, `specFactory.js`, `components/ChartSlot.vue`, `components/Dashboard.vue`, relevant unit/filter presentation helpers; extend frontend tests; modify `frontend/scripts/renderVisualCheck.mjs` and optionally add a separate study-render script.

**Interfaces:** Preserve current createSpec call sites by adding optional third `presentation` argument. `chartLayoutForView(view, availableWidth)` returns card span/height, plot dimensions, ordered full domains and paging policy. `heatmapPresentation(view, {pageIndex,mode}, availableWidth)` returns visible category projection and full-data scale domain, without mutating view. Presentation is local component state only.

- [ ] Write failing layout tests for 72 Y categories ×2 X values: four pages of 20 categories, last12; every category's two cells stay together. Test 24-category threshold, no paging for binned_2d, fixed full-data color domains, source order, empty data, long labels and off-page selections.
- [ ] Run `npm test` for RED. Implement pure layout/presentation helpers, with complete rows prepared before projection; preserve full-data denominator/selection metadata aligned with rows.
- [ ] Replace fixed card heights with spec layout tiers, actual-container-width two/one-column layout at 880px, stable creation order, full-width dense heatmap/multiseries/facet cards, two-line title and wrapping metadata. Keep existing conversation/microphone workflow unchanged.
- [ ] Add accessible Previous/Next/Page/View all controls, 20-category pages, top horizontal continuous legend, ~22px rows, max220px labels, internal full-view scrolling; keep complete data and revision/digest untouched. New source revision with same category domain preserves page; changed domain clamps page.
- [ ] Repair facet wrap with explicit child dimensions and supported autosize. Format percentage_points and correlation distinctly from ratios; new result kinds use column metadata, no Olist branches. Render structured OR filter labels without object-string artifacts.
- [ ] Update static demo to share layout/spec logic, output page/full SVGs and working native buttons, full-row heatmap and bounded full-view scroll. Keep compatibility output names and distinguish full versus paged content.
- [ ] Run frontend suite and build; render actual Olist SVGs, inspect 360/768/1440px layouts and actual Vue cards when browser capability permits. Verify rapid re-render/unmount lifecycle and no horizontal page overflow. Report any unavailable browser acceptance, do not substitute compilation claims.
- [ ] Commit only frontend files after coordination; write frontend report with tests, artifact paths and unresolved visual concerns.

## Task 5: Parent integration and acceptance

**Files:** Parent updates README and creates `docs/superpowers/plans/2026-10-16-study-tools-and-chart-layout-report.md`; no controller product fixes.

- [ ] Review backend and frontend diffs against the approved spec, especially the five Review Focus cases; route corrections to the owning existing agent.
- [ ] Verify frontend consumes actual Task 3 outputs, tool-created charts render, selection/paging/denominators remain semantically correct, and no temporary lookup mismatch is hidden by fixtures.
- [ ] Run final fresh full Python suite, frontend suite/build, both real-data replays, and six-family plus study-result rendering. Independently inspect representative images; use live browser verification if available.
- [ ] Record completed features, performance/accuracy limitations and real voice acceptance gaps; maintain runnable loopback demo and document its restart command.
- [ ] Keep branch/worktree; report no merge/push. No formal-user-study readiness claim until external voice/provider preflight is complete.
