from test_olist_adapter import _load, olist_csvs  # noqa: F401


def test_or_and_same_item_semantics(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("aggregate", {"group_by": [], "metrics": [], "unit": "order",
            "filters": [{"id": "regions", "op": "or", "branches": [
                {"all": [{"field": "customer_state", "op": "eq", "value": "RJ"}]},
                {"all": [{"field": "product_category", "op": "eq", "value": "books"},
                         {"field": "seller_id", "op": "eq", "value": "s2"}]},
            ]}], "measures": [{"id": "delivery", "stat": "mean", "field": "delivery_days"}]})
        assert result["success"], result
        # o1 has books and seller s2 on different items and must not satisfy branch 2.
        assert result["metadata"]["measure_valid_counts"]["delivery"]["all"] == 2
    finally:
        ds.close()


def test_status_inside_or_is_rejected(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("aggregate", {"group_by": [], "metrics": [], "unit": "order",
            "filters": [{"id": "bad", "op": "or", "branches": [{"all": [
                {"field": "order_status", "op": "eq", "value": "canceled"}]},
                {"all": [{"field": "customer_state", "op": "eq", "value": "SP"}]}]}],
            "measures": [{"id": "m", "stat": "mean", "field": "delivery_days"}]})
        assert not result["success"]
    finally:
        ds.close()


def test_nested_or_and_mixed_between_fail_structurally(olist_csvs):
    ds = _load(olist_csvs)
    try:
        nested = {"op": "or", "branches": [{"all": [{"op": "or", "branches": [
            {"all": [{"field": "customer_state", "op": "eq", "value": "SP"}]},
            {"all": [{"field": "customer_state", "op": "eq", "value": "RJ"}]}]}]},
            {"all": [{"field": "customer_state", "op": "eq", "value": "SP"}]}]}
        for condition in (nested, {"field": "purchase_hour", "op": "between", "value": ["x", 1]}):
            result = ds.execute("aggregate", {"group_by": [], "metrics": [], "unit": "order",
                "filters": [condition], "measures": [{"id": "m", "stat": "mean", "field": "delivery_days"}]})
            assert not result["success"]
    finally:
        ds.close()


def test_snapshot_materializes_quantile_rule_and_shared_bounds_are_enforced(olist_csvs):
    from refactor_next.backend.dashboard import Dashboard
    from refactor_next.backend.tools import Toolbox
    ds = _load(olist_csvs)
    try:
        dashboard = Dashboard(ds.description["dataset_id"], ds.description["version"]); tools = Toolbox(ds, dashboard)
        draft = dashboard.begin_draft()
        created = tools.execute("create_chart", {"source": {"tool": "relationship", "arguments": {
            "unit": "item", "x": "price", "y": "freight_value", "representation": "points",
            "filters": [{"id": "middle", "field": "price", "op": "quantile_between", "value": {"lower": .25, "upper": .75}}]}},
            "visual": {"type": "scatter", "encoding": {"x": "x_value", "y": "y_value"}}}, draft)
        assert created["success"], created
        dashboard.commit(draft); draft = dashboard.begin_draft()
        forked = tools.execute("fork_chart", {"view_id": created["payload"]["id"], "scope_mode": "snapshot"}, draft)
        assert forked["success"], forked
        clone = forked["payload"]
        assert all(item["op"] != "quantile_between" for item in clone["source"]["arguments"]["filters"])
        assert {(item["op"], item["value"]) for item in clone["source"]["arguments"]["filters"]} == {("gte", 47.5), ("lte", 105.0)}
        assert clone["metadata"]["materialized_quantile_rules"][0]["id"] == "middle"
        dashboard.commit(draft); before = clone["data"]
        draft = dashboard.begin_draft(); changed = tools.execute("set_analysis_filters", {"filters": [
            {"field": "customer_state", "op": "eq", "value": "RJ"}]}, draft)
        assert changed["success"], changed
        dashboard.commit(draft)
        persisted = next(view for view in dashboard.snapshot()["views"] if view["id"] == clone["id"])
        assert persisted["data"] == before
        draft = dashboard.begin_draft(); too_many = tools.execute("set_analysis_filters", {"filters": [
            {"field": "customer_state", "op": "eq", "value": "SP"} for _ in range(21)]}, draft)
        assert not too_many["success"] and too_many["error"]["code"] == "INVALID_FILTER_VALUE"
    finally:
        ds.close()
