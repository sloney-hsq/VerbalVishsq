## Task 1: Shared predicate and measure contracts

**Files:** Modify `datasets/olist/query_common.py`, `schema.py`, `metrics.py`, `queries.py`, `interface.py`; create `datasets/olist/measure_queries.py` and `predicate_plan.py` for focused logic. Modify `backend/filter_contract.py`, `chart_patch.py`, `tools.py`, `analytics.py` as required by generic contracts. Add `tests/test_study_predicates.py`, `tests/test_study_measures.py`; extend existing tool tests.

**Interfaces:** Public queries preserve `execute(name, arguments, scope)`. New measure definitions and OR/quantile filter shapes are exactly those in the spec. Query helpers remain private to the adapter; expose normalized output `rows/columns/result_kind/metadata` through its existing interface. New metadata must include stable measure definitions and row-aligned valid denominators.

- [ ] Write failing tests with real synthetic adapter fixtures: mean([1,3,9])=13/3, median=3, q=.9 gives 7.8; threshold <=3 gives 2/3; registered total ratio uses matched eligible rows. Test no-data/null, duplicate IDs, invalid unit, four-total-measure cap and SQL-looking values as data only.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_study_predicates.py tests/test_study_measures.py -q`; record RED before implementation.
- [ ] Implement bounded AND/OR validation and one shared predicate plan. Assert order-only OR admits an order with no item; an order whose different items separately satisfy two AND leaves must not match. Keep default delivered explicit and reject status in OR.
- [ ] Implement registered measures and ID-based measure changes; old fixed metrics remain compatible. Exercise dynamic IDs in having/sort/top_k, and source-switch scope preservation with OR groups. Make required-argument checks schema-driven rather than hardcoded metrics.
- [ ] Implement complete-base-population quantile resolution and snapshot materialization. Test independent simultaneous rules, no group/sample influence, EMPTY_REFERENCE_POPULATION, linked recomputation and fixed snapshot boundaries. Reject shared/OR/segment-local quantile rules explicitly.
- [ ] Run focused plus existing analysis/filter/chart tests; commit only owned paths after parent grants commit slot. Report precise commands, RED/GREEN, metadata shapes and concerns.

