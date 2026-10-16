"""Offline six-task study-tool replay. No model or provider calls."""
import argparse
import json
from pathlib import Path
from time import perf_counter

from refactor_next.backend.analytics import load_dataset
from refactor_next.backend.dashboard import Dashboard
from refactor_next.backend.tools import Toolbox

ROOT = Path(__file__).resolve().parents[1]


def run_workflows(data_dir, *, export=None):
    dataset = load_dataset(ROOT / "datasets/olist/interface.py", {"data_dir": str(data_dir)})
    dashboard = Dashboard(dataset.description["dataset_id"], dataset.description["version"])
    tools, events, views = Toolbox(dataset, dashboard), [], {}

    def call(name, args):
        started = perf_counter(); draft = dashboard.begin_draft(); result = tools.execute(name, args, draft)
        if not result["success"]:
            dashboard.discard(draft); raise AssertionError(f"{name}: {result['error']}")
        document = dashboard.commit(draft); payload = result["payload"]
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        events.append({"tool": name, "elapsed_ms": round((perf_counter() - started) * 1000, 2),
            "revision": document["dashboard_revision"], "eligible_count": metadata.get("eligible_count"),
            "valid_count": metadata.get("valid_count", metadata.get("valid_pair_count"))})
        return payload

    def chart(key, tool, arguments, visual):
        view = call("create_chart", {"source": {"tool": tool, "arguments": arguments}, "visual": visual, "title": key})
        views[key] = view; return view

    try:
        regional = chart("regional_delivery_risk", "aggregate", {"group_by": ["customer_state"], "metrics": [], "unit": "order",
            "measures": [{"id": "delivery_p90", "stat": "quantile", "field": "delivery_days", "q": .9}]},
            {"type": "bar", "encoding": {"x": "delivery_p90", "y": "customer_state"}})
        regional = call("update_chart", {"view_id": regional["id"], "analysis_patch": {"measure_changes": {"upsert": [
            {"id": "delivery_p90", "stat": "quantile", "field": "delivery_days", "q": .8}]}}})
        assert regional["source"]["arguments"]["group_by"] == ["customer_state"]
        views["regional_delivery_risk"] = regional
        period = chart("delivery_period_change", "compare_periods", {"output": "series", "grain": "month", "time_field": "order_date",
            "periods": [{"id": "early", "label": "Early", "start": "2017-01-01", "end": "2018-01-01"},
                        {"id": "late", "label": "Late", "start": "2018-01-01", "end": "2019-01-01"}],
            "unit": "order", "metrics": [], "measures": [{"id": "delivery_p90", "stat": "quantile", "field": "delivery_days", "q": .9}]},
            {"type": "line", "encoding": {"x": "bucket_index", "y": "delivery_p90", "color": "period"}})
        period = call("update_chart", {"view_id": period["id"], "analysis_patch": {"set": {"comparison": {
            "reference_period_id": "early", "outputs": ["difference"]}}}})
        assert period["source"]["arguments"]["grain"] == "month"
        views["delivery_period_change"] = period
        review = chart("low_rating_delivery", "compare_segments", {"unit": "order", "metrics": [],
            "segments": [{"id": "low", "label": "Low", "filters": [{"field": "review_score", "op": "lte", "value": 2}]},
                         {"id": "high", "label": "High", "filters": [{"field": "review_score", "op": "gte", "value": 4}]}],
            "measures": [{"id": "delivery_mean", "stat": "mean", "field": "delivery_days"}],
            "comparison": {"reference_segment_id": "high", "outputs": ["difference", "relative_difference"]}},
            {"type": "bar", "encoding": {"x": "segment", "y": "delivery_mean"}})
        revised_segments = review["source"]["arguments"]["segments"]
        revised_segments[0]["filters"][0]["value"] = 1
        review = call("update_chart", {"view_id": review["id"], "analysis_patch": {"set": {"segments": revised_segments}}})
        assert review["source"]["arguments"]["comparison"]["reference_segment_id"] == "high"
        views["low_rating_delivery"] = review
        freight = chart("freight_robustness", "aggregate", {"group_by": ["product_category"], "metrics": [], "unit": "item",
            "measures": [{"id": "freight_share", "stat": "registered_ratio", "formula_id": "freight_share_of_total"}]},
            {"type": "bar", "encoding": {"x": "freight_share", "y": "product_category"}})
        freight = call("update_chart", {"view_id": freight["id"], "analysis_patch": {"measure_changes": {"upsert": [
            {"id": "freight_share", "stat": "mean", "field": "freight_ratio"}]}}})
        views["freight_robustness"] = freight
        assoc = chart("freight_attribute_association", "relationship", {"unit": "item", "x": "product_weight_kg", "y": "freight_value",
            "representation": "points", "correlations": ["pearson", "spearman"], "sampling": {"max_points": 500, "seed": 7},
            "filters": [{"id": "middle", "field": "product_weight_kg", "op": "quantile_between", "value": {"lower": .05, "upper": .95}}]},
            {"type": "scatter", "encoding": {"x": "x_value", "y": "y_value"}})
        call("fork_chart", {"view_id": assoc["id"], "scope_mode": "snapshot"})
        seller_rank = call("create_chart", {"source": {"tool": "aggregate", "arguments": {"group_by": ["seller_id"],
            "metrics": ["order_count"], "top_k": {"dimension": "seller_id", "metric": "order_count", "k": 10, "direction": "desc"}}},
            "visual": {"type": "bar", "encoding": {"x": "seller_id", "y": "order_count"}}, "title": "seller_volume_scope"})
        seller_scope = seller_rank["metadata"]["top_k"]["selected_members"]
        seller = chart("seller_delivery_stability", "distribution", {"unit": "order", "field": "delivery_days", "group_by": "seller_id",
            "filters": [{"field": "seller_id", "op": "in", "value": seller_scope}],
            "output": "quantiles", "quantiles": [.5, .9]}, {"type": "line", "encoding": {"x": "quantile", "y": "value", "color": "group"}})
        seller_filter = seller["source"]["arguments"]["filters"][0]
        seller = call("update_chart", {"view_id": seller["id"], "analysis_patch": {"filter_changes": {"upsert": [
            {"id": seller_filter["id"], "field": "seller_id", "op": "in", "value": seller_scope[:5]}]}}})
        assert seller["source"]["arguments"]["quantiles"] == [.5, .9]
        views["seller_delivery_stability"] = seller
        call("delete_chart", {"view_id": seller_rank["id"]})
        call("set_analysis_filters", {"filters": [{"id": "scope", "op": "or", "branches": [
            {"all": [{"field": "customer_state", "op": "eq", "value": "SP"}]},
            {"all": [{"field": "customer_state", "op": "eq", "value": "RJ"}]}]}]})
        call("undo_dashboard", {})
        if export:
            path = Path(export); path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(views, ensure_ascii=False, default=str), encoding="utf-8")
        return events, dashboard.snapshot()
    finally:
        dataset.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--data-dir", type=Path, required=True); parser.add_argument("--export", type=Path)
    args = parser.parse_args(); events, final = run_workflows(args.data_dir, export=args.export)
    print(json.dumps({"events": events, "revision": final["dashboard_revision"]}, indent=2))
