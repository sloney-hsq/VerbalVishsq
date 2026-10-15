# Olist exploratory adapter report

> Migration-predecessor historical evidence only. This report does not state the current repository verification result; record current final verification in PROGRESS.md when it is available.

## Scope

During the migration-predecessor phase, the Olist implementation was confined to `datasets/olist/interface.py`, `schema.py`, `metrics.py`, `queries.py`, and `__init__.py`, with focused coverage in `tests/test_olist_adapter.py`. That historical integration phase migrated two legacy callers in `tests/test_datasets.py` and `tests/test_dashboard_tools.py`; runtime, response protocol, dashboard, toolbox and frontend production files were not changed in that phase. No commit was created in that phase.

The adapter intentionally exposes exactly two tools: `aggregate` and `compare_segments`. The old `compare_commerce` tool is not retained; callers must migrate to the multi-metric `aggregate` contract.

## Data model and semantics

All nine configured Olist CSVs are versioned and loaded as independently readable `raw_*` DuckDB tables. Geolocation is exposed only as raw data; no distance field is derived.

Persisted canonical tables:

- `order_grain`: one row per raw order, retaining every order status and the requested IDs, timestamps, customer location, item aggregates, revenue, freight, total value, canonical review, payment aggregates, and delivery durations.
- `item_grain`: one row per order item with product, seller, order, customer, review, payment, and delivery context.
- `customer_grain`: one row per `customer_unique_id`.
- `seller_order_grain`: one row per seller/order pair.
- `payment_grain`: one row per source payment record with typed sequence, type, installments, value, order status/date, and customer location context.

Customer and seller ZIP-code prefixes are registered groupable/filterable dimensions and retained on their applicable canonical grains. Order lifecycle fields include `promise_window_days` (estimated delivery minus purchase, only when non-negative) and eligible `late_days = max(actual - estimated, 0)`. Late eligibility requires both actual and estimated delivery to be on or after purchase, so impossible negative promise windows are excluded from the late denominator. Item and seller-order grains retain both lifecycle values; `avg_late_days` still averages late orders only.

Reviews first collapse to one canonical record per order using `review_creation_date DESC NULLS LAST, review_id DESC`. Average score, low/one/five-star ratios, and `review_comment_ratio` all use that same record. Score ratios use canonical reviews with non-null scores; comment ratio uses orders with a canonical review record. Payments still collapse to one order row for safe analytical joins, while `payment_grain` preserves every typed source record for later exploration.

All statuses remain queryable. Both tools add `order_status = delivered` only when neither shared scope, tool filters, nor segment conditions explicitly mention status. Revenue is item price only. `total_order_value` is price plus freight. Week buckets start Monday; time ranges are half-open `[start, end)`. Delivery metrics require complete, non-negative endpoints. `late_ratio` uses only delivered orders with eligible actual/estimated dates, and `avg_late_days` uses only late orders.

Product weight is converted from raw grams to kilograms. Product weight and dimensions that are missing or non-positive become NULL. Item freight ratio is `freight / (price + freight)` and becomes NULL when either component is missing or the denominator is non-positive.

For item-level dimensions, queries first build a `dimension x order` intermediate grain and only then calculate order review/delivery metrics. This prevents item rows from weighting order-level averages. Item measures remain attributed to the matching product/seller segment. `aggregate` accepts zero or one grouping dimension and at most four metrics. Filters support `eq`, `neq`, `gte`, `lte`, `gt`, `lt`, `in`, inclusive `between`, and `is_null`; values are parameter-bound. Time ranges remain half-open.

## TDD evidence

The focused nine-CSV fixture includes an adversarial order with two items, two sellers, two categories, two payment records, and two reviews. Before production changes:

```text
python -m pytest tests/test_olist_adapter.py -q
11 failed in 2.15s
```

Failures were the expected missing `aggregate`/`compare_segments`, registry/grain, loader-cleanup, and diagnostic behavior. The initial implementation and empty-segment regression reached 12 passing tests. The canonical-review/filter/payment/raw-table delta was again run red first (`9 failed, 8 passed`). The ZIP/lifecycle/Task-A delta was verified red (`3 failed, 16 passed`). The final late-eligibility fixture produced the expected four failures while the new `neq`/`gte`/`lte`/`is_null`, NULL-review-date, and combined scope/filter/time/segment parameter-order regressions already passed. Historical focused result:

```text
24 passed in 3.93s
```

The first real-data load exposed an exact-float comparison defect: raw delivered revenue `13221498.11001369` and canonical revenue `13221498.110011635` differed only by aggregation order. Validation now requires exact distinct-order count and tight `isclose` equality for floating sums. The repeated real load succeeded.

## Real Olist smoke

Configured source during this historical smoke test: repository-local ignored Olist data directory. Snapshot version during the final run: `olist-5-8e2b55985d02985e`.

- Fresh load, all nine raw tables, and canonical construction: 4.54 s.
- Raw rows: 99,441 orders; 112,650 items; 103,886 payments; 99,224 reviews; 99,441 customers; 32,951 products; 3,095 sellers; 71 translations; 1,000,163 geolocation rows.
- Canonical rows: 99,441 orders; 112,650 items; 96,096 unique customers; 100,010 seller/order rows; 103,886 payment rows.
- Default delivered totals: 96,478 orders and BRL 13,221,498.11 revenue. Canonical-review average was 4.15579 and comment ratio 0.42366.
- Task A (SP, `order_week`, 2017-10-01 through 2018-04-01 exclusive, `order_count`, `low_score_ratio`, `avg_delivery_days`, `late_ratio`): 27 rows and 15,495 orders in 0.010 s. The first bucket is Monday 2017-09-25 because it contains purchases on Sunday 2017-10-01.
- Task B (RJ `office_furniture` versus `bed_bath_table`): two segment rows in 0.014 s. Order counts were 212 and 1,357; revenue was BRL 45,212.32 and BRL 144,251.79; canonical-review comment ratios were 0.5236 and 0.5415.
- Customer ZIP-prefix grouping with an SP filter returned successfully in 0.017 s.

No data rows beyond small verification samples were dumped.

## Full-suite compatibility result

In the migration-predecessor integration phase, the complete `tests` suite reported **121 passed** with one pre-existing Starlette deprecation warning. No compatibility-only third tool was added. This is historical evidence, not a claim about the current repository state.
