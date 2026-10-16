from test_olist_adapter import _load, olist_csvs  # noqa: F401


def test_segment_measure_comparison_wide_columns(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("compare_segments", {"unit": "order", "metrics": [],
            "measures": [{"id": "late", "stat": "threshold_ratio", "field": "delivery_days", "op": "gt", "value": 7}],
            "segments": [{"id": "sp", "label": "SP", "filters": [{"field": "customer_state", "op": "eq", "value": "SP"}]},
                         {"id": "rj", "label": "RJ", "filters": [{"field": "customer_state", "op": "eq", "value": "RJ"}]}],
            "comparison": {"reference_segment_id": "sp", "outputs": ["difference", "relative_difference", "percentage_point_difference"]}})
        assert result["success"], result
        rj = next(row for row in result["rows"] if row["segment_id"] == "rj")
        assert rj["late"] == .5 and rj["late__difference"] == (0.5 - 1/3)
        assert rj["late__percentage_point_difference"] == 100 * (0.5 - 1/3)
        assert result["columns"]["late__percentage_point_difference"]["unit"] == "percentage_points"
        mixed = ds.execute("compare_segments", {"unit": "order", "metrics": ["order_count"],
            "measures": [{"id": "late", "stat": "threshold_ratio", "field": "delivery_days", "op": "gt", "value": 7}],
            "segments": [{"id": "sp", "label": "SP", "filters": [{"field": "customer_state", "op": "eq", "value": "SP"}]},
                         {"id": "rj", "label": "RJ", "filters": [{"field": "customer_state", "op": "eq", "value": "RJ"}]}],
            "comparison": {"reference_segment_id": "sp", "outputs": ["difference"]}})
        assert mixed["success"], mixed
        mixed_rj = next(row for row in mixed["rows"] if row["segment_id"] == "rj")
        assert mixed_rj["order_count"] == 2 and mixed_rj["order_count__difference"] == -1
    finally:
        ds.close()


def test_fixed_only_breakdown_comparison_pairs_same_key_and_leaves_missing_null(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("compare_segments", {"segments": [
            {"id": "sp", "label": "SP", "filters": [{"field": "customer_state", "op": "eq", "value": "SP"}]},
            {"id": "rj", "label": "RJ", "filters": [{"field": "customer_state", "op": "eq", "value": "RJ"}]}],
            "metrics": ["avg_delivery_days"], "breakdown": "order_month",
            "comparison": {"reference_segment_id": "sp", "outputs": ["difference", "relative_difference"]}})
        assert result["success"], result
        rj = [row for row in result["rows"] if row["segment_id"] == "rj"]
        assert rj and all(row["avg_delivery_days__difference"] is None for row in rj)
    finally:
        ds.close()


def test_fixed_only_legacy_segments_honor_comparison(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("compare_segments", {"segments": [
            {"name": "SP", "customer_state": "SP"}, {"name": "RJ", "customer_state": "RJ"}],
            "metrics": ["avg_delivery_days"],
            "comparison": {"reference_segment_id": "legacy-1", "outputs": ["difference"]}})
        assert result["success"], result
        assert result["rows"][1]["avg_delivery_days__difference"] == 3
    finally:
        ds.close()


def test_approved_customer_state_composition_is_complete(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("compare_segments", {"segments": [
            {"id": "s1", "label": "Seller 1", "filters": [{"field": "seller_id", "op": "eq", "value": "s1"}]},
            {"id": "s2", "label": "Seller 2", "filters": [{"field": "seller_id", "op": "eq", "value": "s2"}]}],
            "metrics": ["order_count"], "breakdown": "customer_state", "normalization": "within_segment"})
        assert result["success"], result
        for segment in {row["segment_id"] for row in result["rows"]}:
            assert abs(sum(row["share"] for row in result["rows"] if row["segment_id"] == segment) - 1) < 1e-12
        assert result["metadata"]["composition_complete"] is True
        assert result["metadata"]["segment_denominator"] == "order_count"
    finally:
        ds.close()


def test_segment_quantile_rule_uses_pooled_union_reference(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("compare_segments", {"unit": "item", "metrics": [],
            "filters": [{"id": "middle", "field": "price", "op": "quantile_between", "value": {"lower": .25, "upper": .75}}],
            "segments": [{"id": "s1", "label": "S1", "filters": [{"field": "seller_id", "op": "eq", "value": "s1"}]},
                         {"id": "s2", "label": "S2", "filters": [{"field": "seller_id", "op": "eq", "value": "s2"}]}],
            "measures": [{"id": "price_mean", "stat": "mean", "field": "price"}]})
        assert result["success"], result
        rule = result["metadata"]["quantile_rules"][0]
        assert rule["base_valid_count"] == 8 and rule["bounds"] == {"lower": 47.5, "upper": 105.0}
    finally:
        ds.close()
