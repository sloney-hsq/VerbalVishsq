"""Olist distribution, relationship and richer query regressions."""
import pytest

from test_olist_adapter import _load, olist_csvs  # noqa: F401


def test_two_dimensions_having_and_fixed_top_k(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("aggregate", {"group_by": ["customer_state", "order_month"],
            "metrics": ["late_ratio"], "having": [{"field": "late_eligible_order_count", "op": "gte", "value": 1}],
            "top_k": {"dimension": "customer_state", "metric": "order_count", "k": 1, "direction": "desc"}})
        assert result["success"], result
        assert {row["customer_state"] for row in result["rows"]} == {"SP"}
        assert all("late_eligible_order_count" not in row for row in result["rows"])
    finally:
        ds.close()


def test_top_k_ranks_distinct_orders_before_second_dimension(olist_csvs):
    ds = _load(olist_csvs)
    try:
        ds._interface.connection.execute("INSERT INTO item_grain SELECT * REPLACE ('toys' AS product_category, 3 AS order_item_id) FROM item_grain WHERE order_id = 'o6' AND order_item_id = 1")
        result = ds.execute("aggregate", {"group_by": ["customer_state", "product_category"],
            "metrics": ["order_count"], "top_k": {"dimension": "customer_state", "metric": "order_count", "k": 1, "direction": "desc"}})
        assert result["success"], result
        assert {row["customer_state"] for row in result["rows"]} == {"SP"}
        assert result["metadata"]["top_k"]["selected_members"] == ["SP"]
    finally:
        ds.close()


def test_score_breakdown_rejects_noncount_metric_and_normalization_without_breakdown(olist_csvs):
    ds = _load(olist_csvs)
    try:
        segments = [{"customer_state": "SP"}, {"customer_state": "RJ"}]
        bad = ds.execute("compare_segments", {"segments": segments, "metrics": ["avg_delivery_days"], "breakdown": "review_score"})
        assert not bad["success"] and bad["error"]["code"] == "INCOMPATIBLE_GRAIN"
        bad = ds.execute("compare_segments", {"segments": segments, "metrics": ["reviewed_order_count"], "normalization": "within_segment"})
        assert not bad["success"] and bad["error"]["code"] == "INCOMPATIBLE_GRAIN"
    finally:
        ds.close()


def test_aggregate_reports_effective_scope_and_metric_denominator(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("aggregate", {"group_by": ["customer_state"], "metrics": ["late_ratio"]})
        assert result["success"], result
        assert result["metadata"]["effective_filters"] == [{"field": "order_status", "op": "eq", "value": "delivered"}]
        assert result["metadata"]["metric_valid_counts"]["late_ratio"] == {"SP": 2, "RJ": 2}
        explicit = ds.execute("aggregate", {"group_by": [], "metrics": ["order_count"],
            "filters": [{"field": "order_status", "op": "eq", "value": "canceled"}]})
        assert explicit["metadata"]["default_scope_applied"] is False
    finally:
        ds.close()


def test_segment_score_composition(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("compare_segments", {"segments": [
            {"id": "sp", "label": "SP", "filters": [{"field": "customer_state", "op": "eq", "value": "SP"}]},
            {"id": "rj", "label": "RJ", "filters": [{"field": "customer_state", "op": "eq", "value": "RJ"}]}],
            "metrics": ["reviewed_order_count"], "breakdown": "review_score", "normalization": "within_segment"})
        assert result["success"], result
        assert len(result["rows"]) == 10
        assert sum(row["share"] for row in result["rows"] if row["segment_id"] == "sp") == pytest.approx(1)
        assert result['columns']['breakdown']['type'] == 'ordinal'
        assert result['columns']['breakdown']['sort_order'] == [1, 2, 3, 4, 5]
        assert result['metadata']['metric_valid_counts']['reviewed_order_count']['sp:1'] >= 0
    finally:
        ds.close()


def test_legacy_and_typed_segment_metadata_tracks_scope_and_valid_counts(olist_csvs):
    ds = _load(olist_csvs)
    try:
        legacy = ds.execute('compare_segments', {'segments': [
            {'customer_state': 'SP'}, {'customer_state': 'RJ'}], 'metrics': ['avg_delivery_days']})
        assert legacy['success'], legacy
        assert legacy['metadata']['metric_valid_counts']['avg_delivery_days']['legacy-1'] > 0
        assert legacy['metadata']['effective_filters_by_segment']['legacy-1'][0] == {
            'field': 'order_status', 'op': 'eq', 'value': 'delivered'}
        typed = ds.execute('compare_segments', {'segments': [
            {'id': 'cancel', 'label': 'Canceled', 'filters': [{'field': 'order_status', 'op': 'eq', 'value': 'canceled'}]},
            {'id': 'sp', 'label': 'SP', 'filters': [{'field': 'customer_state', 'op': 'eq', 'value': 'SP'}]}],
            'metrics': ['order_count']})
        assert typed['success'], typed
        assert typed['metadata']['default_scope_applied_by_segment'] == {'cancel': False, 'sp': True}
        assert typed['metadata']['effective_filters_by_segment']['cancel'] == [
            {'field': 'order_status', 'op': 'eq', 'value': 'canceled'}]
        assert typed['metadata']['metric_valid_counts']['order_count']['sp'] > 0
    finally:
        ds.close()


def test_order_distribution_deduplicates_items(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("distribution", {"unit": "order", "field": "delivery_days", "output": "histogram", "bins": {"count": 3}})
        assert result["success"], result
        assert sum(row["count"] for row in result["rows"]) == 5
        assert result["metadata"]["valid_count"] == 5
    finally:
        ds.close()


def test_box_continuous_quantiles_and_whiskers():
    from refactor_next.datasets.olist.distributions import summarize_box
    assert summarize_box([1, 2, 3, 4, 100]) == {"q1": 2, "median": 3, "q3": 4,
        "whisker_low": 1, "whisker_high": 4, "outlier_count": 1}


def test_histogram_explicit_bounds_and_empty_sample(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("distribution", {"unit": "item", "field": "price", "output": "histogram",
            "bins": {"edges": [0, 100, 200]}})
        assert result["success"], result
        assert sum(row["count"] for row in result["rows"]) + result["metadata"]["group_counts"]["None"]["overflow_count"] == result["metadata"]["valid_count"]
        assert next(row for row in result["rows"] if row["bin_start"] == 100)["count"] >= 1
        empty = ds.execute("distribution", {"unit": "order", "field": "delivery_days", "output": "histogram",
            "filters": [{"field": "customer_state", "op": "eq", "value": "ZZ"}]})
        assert empty["success"] and empty["rows"] == [] and empty["metadata"]["valid_count"] == 0
    finally:
        ds.close()


def test_invalid_grain_and_bin_limits(olist_csvs):
    ds = _load(olist_csvs)
    try:
        assert not ds.execute("relationship", {"unit": "order", "x": "product_weight_kg", "y": "delivery_days", "representation": "points"})["success"]
        assert not ds.execute("distribution", {"unit": "item", "field": "price", "output": "histogram", "bins": {"count": 101}})["success"]
        assert not ds.execute("relationship", {"unit": "item", "x": "price", "y": "freight_value", "representation": "points", "sampling": {"max_points": 5001}})["success"]
    finally:
        ds.close()


def test_invalid_canonical_score_is_missing_not_a_numeric_observation(olist_csvs):
    ds = _load(olist_csvs)
    try:
        ds._interface.connection.execute("UPDATE order_grain SET review_score = 8 WHERE order_id = 'o1'")
        result = ds.execute("distribution", {"unit": "order", "field": "review_score", "output": "box_summary"})
        assert result["success"], result
        assert result["metadata"]["valid_count"] == 3
        assert result["metadata"]["missing_count"] == 2
    finally:
        ds.close()


def test_invalid_bins_rejected_on_empty_and_constant_data(olist_csvs):
    ds = _load(olist_csvs)
    try:
        empty_filter = [{"field": "customer_state", "op": "eq", "value": "ZZ"}]
        for filters in (empty_filter, [{"field": "price", "op": "eq", "value": 100}]):
            for bins in ({"count": 0}, {"step": -1}):
                result = ds.execute("distribution", {"unit": "item", "field": "price", "output": "histogram",
                    "filters": filters, "bins": bins})
                assert not result["success"] and result["error"]["code"] == "INVALID_FILTER_VALUE"
    finally:
        ds.close()


def test_explicit_status_is_reported_without_delivered_default(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("distribution", {"unit": "item", "field": "price", "output": "box_summary",
            "filters": [{"field": "order_status", "op": "eq", "value": "canceled"}]})
        assert result["success"], result
        assert result["metadata"]["default_scope_applied"] is False
        assert result["metadata"]["effective_filters"] == [{"field": "order_status", "op": "eq", "value": "canceled"}]
    finally:
        ds.close()


def test_relationship_pair_counts_and_sampling(olist_csvs):
    ds = _load(olist_csvs)
    try:
        args = {"unit": "item", "x": "product_weight_kg", "y": "freight_value",
                "representation": "points", "sampling": {"max_points": 3, "seed": 7}}
        one = ds.execute("relationship", args)
        two = ds.execute("relationship", args)
        assert one["success"], one
        assert [row["observation_id"] for row in one["rows"]] == [row["observation_id"] for row in two["rows"]]
        assert one["metadata"]["valid_pair_count"] + one["metadata"]["missing_pair_count"] == one["metadata"]["eligible_count"]
        cells = ds.execute("relationship", {k: v for k, v in {**args, "representation": "binned_2d", "bins": {"x_count": 2, "y_count": 2}}.items() if k != "sampling"})
        assert cells["success"], cells
        assert sum(row["count"] for row in cells["rows"]) == one["metadata"]["valid_pair_count"]
    finally:
        ds.close()
