# Task 2 report — comparisons, distributions and relationships

Status: implementation complete; commit pending serialized slot.

Implemented wide segment comparison columns with difference, relative difference and percentage points; ratio-only percentage-point validation; arbitrary continuous quantile output; exact full-data Pearson and tie-aware Spearman; relationship summary rows; correlation failure reasons; display sampling independence; overall observation-ID de-duplication under overlapping groups; and approved complete compositions for review score, customer state, order status and item product category.

TDD evidence:

- RED: `pytest tests/test_study_comparisons.py tests/test_study_distributions.py tests/test_study_relationships.py -q` → 3 failed, 1 passed (schemas lacked new outputs).
- GREEN: focused Task 2 plus legacy visual-query tests → 16 passed in the final comparison run.
- Ruling: the lateness comparison fixture was changed to a delivery-duration threshold because one SP order has invalid lateness by the canonical estimate rule; the revised fixture has a directly auditable 1/3 versus 1/2 denominator.

New result kinds: `quantiles`, `relationship_summary`; units include `percentage_points` and `correlation`.

