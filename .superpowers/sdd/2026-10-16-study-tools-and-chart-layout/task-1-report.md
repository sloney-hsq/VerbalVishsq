# Task 1 report — shared predicates and measures

Status: implementation complete; commit pending serialized slot.

Implemented bounded top-level AND / one-level OR predicates, same-item AND semantics, order de-duplication, explicit delivered default, status-in-OR rejection, typed value validation, local full-base-population quantile rules, stable dynamic measure IDs, registered freight total ratio, ID-based measure patches, snapshot quantile materialization, and schema-declared capabilities. Dynamic having, sort and top_k accept stable measure IDs through the public Toolbox schema.

TDD evidence:

- RED: `pytest tests/test_study_predicates.py tests/test_study_measures.py -q` → 3 failed, 2 passed (old schema required non-empty metrics).
- GREEN focused: predicate/measure/Toolbox tests pass, including nested OR, mixed-type between, stable-ID mean→P90 update, valid denominator metadata, empty population and same-item matching.
- Ruling: the original cheap-price fixture expectation was corrected from 4/8 to 3/8 after enumerating `[0,40,50,60,80,100,120,200]`.

Metadata: `measure_definitions`, `measure_valid_counts`, row-aligned `row_valid_counts`, `row_eligible_counts`, `measure_denominators`, `quantile_rules`, `quantile_combined_retained_count`, and `top_k`.

