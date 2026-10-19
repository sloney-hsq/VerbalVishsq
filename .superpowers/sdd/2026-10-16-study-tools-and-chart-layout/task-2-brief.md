## Task 2: Segment, distribution and relationship extensions

**Files:** Modify `datasets/olist/interface.py`, `distributions.py`, `relationships.py`, `measure_queries.py`; extend result validation in `backend/analytics.py` and chart validation in existing backend modules; add `tests/test_study_comparisons.py`, `tests/test_study_distributions.py`, `tests/test_study_relationships.py`.

**Interfaces:** Consume Task 1 predicates/measures and stable IDs. Preserve wide segment rows; derived columns use `id__difference`, `id__relative_difference`, `id__percentage_point_difference`. Produce new result kinds `quantiles` and `relationship_summary`; declare quantitative columns, source semantics, units `ratio`, `percentage_points`, `correlation`, and validity metadata.

- [ ] Write failing tests: .15 versus .10 yields .05 difference, .5 relative, 5 percentage points; zero/null references yield null relative; missing breakdown references remain null. Group-overlap metadata and valid-count denominator survive comparisons.
- [ ] Write failing quantile output and Pearson/Spearman tests with ties, constant arrays, invalid pairs and grouped overlap. Assert correlation values do not depend on display sample seed or budget.
- [ ] Run focused tests and capture RED; implement spec-defined comparison and quantiles, using continuous full-data quantiles. Add only the approved complete categorical compositions; overlapping order-category breakdowns remain non-normalizable.
- [ ] Implement optional complete-data correlations and summary representation. Test summary rejects sampling/bins, n<2 and zero variance return reasons, and overall statistics de-duplicate observations across overlapping groups.
- [ ] Run tests for all touched interfaces plus Education and legacy tools; commit after coordination. Send frontend the final metadata keys, without changing its files.

