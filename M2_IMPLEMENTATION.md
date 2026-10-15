# Milestone 2 Implementation Contract

## Outcome

M2 makes the existing visual layer consume dataset result metadata, removes Olist-specific frontend behavior, and materializes the Olist initial dashboard through the same validated dataset-tool and `create_chart` path used during conversation.

M2 does not change `backend/dashboard.py`, `backend/response_protocol.py`, Olist metric definitions, response authority, study conditions, RAG, Redis, MCP, or chart types.

## T16 — Metadata-driven visualization

`frontend/src/specFactory.js` owns generic presentation of result columns.

- Encoding type, title, unit and description come from `view.columns[field]`.
- Quantitative formats are selected from metadata unit, never from field names:
  - `ratio`: percent axis and tooltip formatting while the row stays numeric.
  - `BRL` and BRL-derived units: numeric currency-scale formatting; the title retains the unit.
  - `days`, `points`, `kg`: decimal formatting.
  - counts (`orders`, `items`, `customers`, `count`): integer formatting.
  - `cm3`: grouped integer formatting.
- Filter labels resolve from `dimension_index`, categorized `dimensions`, or legacy `resources[*].fields`.
- Filter display supports scalar operators, `in`, `between`, and `is_null` without dataset field-name branches.
- Missing/invalid metadata remains a visible error.

## T17 — Remove frontend Olist conditionals

- Remove the `low_score_ratio` badge and threshold logic from `ChartSlot.vue`.
- `highlightSpec.js` keeps only generic `x`, `series`, and `color` aliases.
- Highlight inference checks the view x/color fields and the actual result columns/data keys; it does not list order, category, state, review, or other Olist fields.
- Existing structured `{field, value}` and `{x_value, series_value}` contracts remain supported.
- Preserve current Vue layout and component styles.

Acceptance scan over `frontend/src` must find no behavior branch for `low_score_ratio`, `late_ratio`, `order_week`, `order_month`, `order_date`, `product_category`, `customer_state`, or `review_score`.

## T18 — Initial dashboard through formal tools

The optional `initial_dashboard` list lives in dataset deployment configuration. It contains ordinary `create_chart` arguments; no result rows are stored in configuration or frontend code.

At `AnalysisSession` construction:

1. Create one dashboard draft.
2. For every configured view, call `Toolbox.execute("create_chart", args, draft)`.
3. If any view fails, discard the draft and fail session construction with the structured tool message. No partial view is visible.
4. If every view succeeds, commit the draft once. Five initial views therefore produce one revision.
5. With no configuration, preserve the existing empty revision-0 dashboard.

Olist configuration defines five views:

1. Monthly Orders Trend.
2. Average Review Score by State.
3. Orders by State.
4. Category Revenue (Top 15).
5. Monthly Average Delivery Days.

All five sources call `aggregate`; later shared filters re-execute the stored sources normally. Education remains empty unless its own configuration opts in.

## Testing and evidence

Use TDD:

- Frontend RED tests first for generic formats, filter metadata, generic highlight inference, and absence of field-specific behavior.
- Backend RED tests first for five successful tool-driven views, one atomic revision, invalid-config rollback, and the no-config baseline.
- Run full Python tests, full frontend tests, production build, Olist startup/materialization smoke, and a final read-only review.

