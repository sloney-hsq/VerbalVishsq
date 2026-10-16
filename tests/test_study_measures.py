from test_olist_adapter import _load, olist_csvs  # noqa: F401


def test_dynamic_measures_keep_stable_ids_and_denominators(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("aggregate", {
            "group_by": [], "metrics": [], "unit": "item", "measures": [
                {"id": "price_mean", "stat": "mean", "field": "price"},
                {"id": "price_median", "stat": "median", "field": "price"},
                {"id": "price_p90", "stat": "quantile", "field": "price", "q": .9},
                {"id": "cheap_share", "stat": "threshold_ratio", "field": "price", "op": "lte", "value": 50},
            ]})
        assert result["success"], result
        assert result["rows"][0] == {"price_mean": 81.25, "price_median": 70.0,
                                      "price_p90": 144.0, "cheap_share": .375}
        assert result["metadata"]["measure_valid_counts"]["price_mean"]["all"] == 8
        assert result["columns"]["price_p90"]["source_field"] == "price"
    finally:
        ds.close()


def test_registered_ratio_uses_matched_rows_and_empty_is_null(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("aggregate", {"group_by": [], "metrics": [], "unit": "item",
            "measures": [{"id": "freight_share", "stat": "registered_ratio",
                          "formula_id": "freight_share_of_total"}]})
        assert result["success"], result
        assert result["rows"][0]["freight_share"] == 90 / 740
        empty = ds.execute("aggregate", {"group_by": [], "metrics": [], "unit": "item",
            "filters": [{"field": "price", "op": "gt", "value": 9999}],
            "measures": [{"id": "m", "stat": "mean", "field": "price"}]})
        assert empty["success"] and empty["rows"][0]["m"] is None
    finally:
        ds.close()


def test_measure_validation(olist_csvs):
    ds = _load(olist_csvs)
    try:
        duplicate = ds.execute("aggregate", {"group_by": [], "metrics": [], "unit": "item",
            "measures": [{"id": "m", "stat": "mean", "field": "price"},
                         {"id": "m", "stat": "median", "field": "price"}]})
        assert not duplicate["success"]
        wrong_unit = ds.execute("aggregate", {"group_by": [], "metrics": [], "unit": "order",
            "measures": [{"id": "m", "stat": "mean", "field": "price"}]})
        assert not wrong_unit["success"]
        for reserved in ("record_count", "period", "segment", "order_count"):
            collision = ds.execute("aggregate", {"group_by": [], "metrics": ["order_count"], "unit": "order",
                "measures": [{"id": reserved, "stat": "mean", "field": "delivery_days"}]})
            assert not collision["success"] and "reserved id" in collision["error"]["message"]
    finally:
        ds.close()


def test_dynamic_measure_having_sort_topk_and_toolbox_patch(olist_csvs):
    from refactor_next.backend.dashboard import Dashboard
    from refactor_next.backend.tools import Toolbox
    ds = _load(olist_csvs)
    try:
        args = {"group_by": ["customer_state"], "metrics": [], "unit": "order",
            "measures": [{"id": "delivery_stat", "stat": "mean", "field": "delivery_days"}],
            "having": [{"field": "delivery_stat", "op": "gt", "value": 5}],
            "sort": {"field": "delivery_stat", "direction": "desc"},
            "top_k": {"dimension": "customer_state", "metric": "delivery_stat", "k": 2, "direction": "desc"}}
        result = ds.execute("aggregate", args)
        assert result["success"], result
        assert [row["customer_state"] for row in result["rows"]] == ["RJ"]
        dashboard = Dashboard(ds.description["dataset_id"], ds.description["version"])
        toolbox = Toolbox(ds, dashboard); draft = dashboard.begin_draft()
        created = toolbox.execute("create_chart", {"source": {"tool": "aggregate", "arguments": args},
            "visual": {"type": "bar", "encoding": {"x": "customer_state", "y": "delivery_stat"}}}, draft)
        assert created["success"], created
        dashboard.commit(draft); draft = dashboard.begin_draft()
        updated = toolbox.execute("update_chart", {"view_id": created["payload"]["id"],
            "analysis_patch": {"measure_changes": {"upsert": [
                {"id": "delivery_stat", "stat": "quantile", "field": "delivery_days", "q": .9}]}}}, draft)
        assert updated["success"], updated
        assert updated["payload"]["source"]["arguments"]["measures"][0]["id"] == "delivery_stat"
    finally:
        ds.close()


def test_eligible_counts_include_missing_and_mixed_controls_use_measure_id(olist_csvs):
    ds = _load(olist_csvs)
    try:
        missing = ds.execute("aggregate", {"group_by": [], "metrics": [], "unit": "order",
            "measures": [{"id": "score", "stat": "mean", "field": "review_score"}]})
        assert missing["metadata"]["row_eligible_counts"] == [5]
        assert missing["metadata"]["row_valid_counts"] == [{"score": 4}]
        mixed = ds.execute("aggregate", {"group_by": ["customer_state"], "metrics": ["order_count"], "unit": "order",
            "measures": [{"id": "delivery", "stat": "mean", "field": "delivery_days"}],
            "having": [{"field": "order_count", "op": "gte", "value": 2}],
            "sort": {"field": "delivery", "direction": "desc"}})
        assert mixed["success"], mixed
        assert mixed["rows"] == [{"customer_state": "RJ", "order_count": 2, "delivery": 8.0},
                                  {"customer_state": "SP", "order_count": 3, "delivery": 5.0}]
        assert mixed["metadata"]["row_valid_counts"] == [{"order_count": 2, "delivery": 2},
                                                           {"order_count": 3, "delivery": 3}]
        hidden_fixed = ds.execute("aggregate", {"group_by": ["customer_state"], "metrics": [], "unit": "order",
            "measures": [{"id": "delivery", "stat": "mean", "field": "delivery_days"}],
            "having": [{"field": "order_count", "op": "gte", "value": 3}]})
        assert hidden_fixed["success"], hidden_fixed
        assert hidden_fixed["rows"] == [{"customer_state": "SP", "delivery": 5.0}]
        assert "order_count" not in hidden_fixed["columns"]
        assert hidden_fixed["metadata"]["row_valid_counts"] == [{"order_count": 3, "delivery": 3}]
        assert hidden_fixed["metadata"]["row_eligible_counts"] == [3]
    finally:
        ds.close()


def test_mixed_aggregate_materializes_local_quantile_before_fixed_and_dynamic_queries(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("aggregate", {"group_by": ["seller_id"], "metrics": ["item_count"], "unit": "item",
            "filters": [{"id": "middle", "field": "price", "op": "quantile_between",
                         "value": {"lower": .25, "upper": .75}}],
            "measures": [{"id": "price_mean", "stat": "mean", "field": "price"}],
            "sort": {"field": "seller_id", "direction": "asc"}})
        assert result["success"], result
        assert result["rows"] == [
            {"seller_id": "s1", "item_count": 2, "price_mean": 90.0},
            {"seller_id": "s2", "item_count": 2, "price_mean": 55.0},
        ]
        assert result["metadata"]["quantile_rules"][0]["bounds"] == {"lower": 47.5, "upper": 105.0}
    finally:
        ds.close()


def test_mixed_top_k_ranks_over_more_than_one_hundred_groups(olist_csvs):
    ds = _load(olist_csvs)
    try:
        ds._interface.con.execute("""
            INSERT INTO order_grain
            SELECT base.* REPLACE (
                'synthetic-' || CAST(i AS VARCHAR) AS order_id,
                'STATE-' || lpad(CAST(i AS VARCHAR), 3, '0') AS customer_state,
                CAST(i AS DOUBLE) AS delivery_days)
            FROM range(150) AS generated(i)
            CROSS JOIN (SELECT * FROM order_grain LIMIT 1) AS base
        """)
        result = ds.execute("aggregate", {"group_by": ["customer_state"], "metrics": ["order_count"], "unit": "order",
            "measures": [{"id": "delivery", "stat": "mean", "field": "delivery_days"}],
            "having": [{"field": "order_count", "op": "gte", "value": 1}],
            "top_k": {"dimension": "customer_state", "metric": "delivery", "k": 1, "direction": "desc"}})
        assert result["success"], result
        assert result["rows"] == [{"customer_state": "STATE-149", "order_count": 1, "delivery": 149.0}]
        assert result["metadata"]["top_k"]["selected_members"] == ["STATE-149"]
    finally:
        ds.close()
