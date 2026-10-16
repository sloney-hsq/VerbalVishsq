"""Focused regression tests for the exploratory Olist dataset adapter."""
from __future__ import annotations

import csv
from datetime import date
import importlib
import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
INTERFACE = ROOT / "datasets" / "olist" / "interface.py"


def _write_csv(directory: Path, name: str, header: list[str], rows: list[list[object]]) -> None:
    with (directory / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture()
def olist_csvs(tmp_path: Path) -> Path:
    _write_csv(
        tmp_path,
        "olist_orders_dataset.csv",
        [
            "order_id", "customer_id", "order_status", "order_purchase_timestamp",
            "order_approved_at", "order_delivered_carrier_date",
            "order_delivered_customer_date", "order_estimated_delivery_date",
        ],
        [
            ["o1", "c1", "delivered", "2017-10-02 10:00:00", "2017-10-03 10:00:00", "2017-10-04 10:00:00", "2017-10-10 10:00:00", "2017-10-09 10:00:00"],
            ["o2", "c2", "delivered", "2017-11-06 11:00:00", "2017-11-06 11:00:00", "2017-11-08 11:00:00", "2017-11-11 11:00:00", "2017-11-15 11:00:00"],
            ["o3", "c3", "delivered", "2018-01-08 12:00:00", "2018-01-09 12:00:00", "", "2018-01-10 12:00:00", "2018-01-07 12:00:00"],
            ["o4", "c4", "delivered", "2018-02-05 13:00:00", "2018-02-06 13:00:00", "2018-02-07 13:00:00", "2018-02-15 13:00:00", "2018-02-12 13:00:00"],
            ["o5", "c5", "canceled", "2018-03-05 14:00:00", "", "", "", "2018-03-20 14:00:00"],
            ["o6", "c6", "delivered", "2018-03-12 15:00:00", "2018-03-12 15:00:00", "2018-03-14 15:00:00", "2018-03-18 15:00:00", "2018-03-20 15:00:00"],
        ],
    )
    _write_csv(
        tmp_path,
        "olist_order_items_dataset.csv",
        ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"],
        [
            ["o1", 1, "p1", "s1", "2017-10-05", 100, 10],
            ["o1", 2, "p2", "s2", "2017-10-05", 50, 5],
            ["o2", 1, "p1", "s1", "2017-11-08", 200, 20],
            ["o3", 1, "p3", "s1", "2018-01-10", 80, 0],
            ["o3", 2, "p4", "s1", "2018-01-10", 0, 0],
            ["o4", 1, "p1", "s1", "2018-02-08", 120, 30],
            ["o5", 1, "p1", "s1", "2018-03-08", 999, 1],
            ["o6", 1, "p2", "s2", "2018-03-14", 60, 15],
            ["o6", 2, "p1", "s1", "2018-03-14", 40, 10],
        ],
    )
    _write_csv(
        tmp_path,
        "olist_order_payments_dataset.csv",
        ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"],
        [
            ["o1", 1, "credit_card", 2, 100], ["o1", 2, "credit_card", 1, 65],
            ["o2", 1, "boleto", 1, 220],
            ["o3", 1, "credit_card", 1, 40], ["o3", 2, "debit_card", 1, 40],
            ["o4", 1, "voucher", 1, 100], ["o4", 2, "voucher", 1, 50],
            ["o5", 1, "credit_card", 1, 1000],
            ["o6", 1, "credit_card", 3, 125],
        ],
    )
    _write_csv(
        tmp_path,
        "olist_order_reviews_dataset.csv",
        ["review_id", "order_id", "review_score", "review_comment_title", "review_comment_message", "review_creation_date", "review_answer_timestamp"],
        [
            ["r1", "o1", 5, "older", "great", "2017-10-12", "2017-10-12"],
            ["r2", "o1", 1, "", "bad", "2017-10-12", "2017-10-13"],
            ["r3", "o2", 5, "", "", "2017-11-12", "2017-11-13"],
            ["r9", "o2", 1, "", "null-date must lose", "", "2017-11-14"],
            ["r4", "o4", 1, "late", "", "2018-02-16", "2018-02-17"],
            ["r5", "o5", 2, "", "", "2018-03-06", "2018-03-07"],
            ["r6", "o6", 5, "", "", "2018-03-19", "2018-03-20"],
        ],
    )
    _write_csv(
        tmp_path,
        "olist_customers_dataset.csv",
        ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"],
        [
            ["c1", "u1", 1000, "sao paulo", "SP"], ["c2", "u1", 1000, "sao paulo", "SP"],
            ["c3", "u2", 1100, "", "SP"], ["c4", "u3", 2000, "rio de janeiro", "RJ"],
            ["c5", "u4", 2000, "rio de janeiro", "RJ"], ["c6", "u5", 2100, "niteroi", "RJ"],
        ],
    )
    _write_csv(
        tmp_path,
        "olist_products_dataset.csv",
        [
            "product_id", "product_category_name", "product_name_lenght", "product_description_lenght",
            "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm",
        ],
        [
            ["p1", "livros", 10, 100, 1, 1000, 10, 10, 10],
            ["p2", "eletronicos", 20, 200, 2, 2000, 10, 10, 30],
            ["p3", "brinquedos", 30, 300, 3, 500, 10, 10, 10],
            ["p4", "brinquedos", 40, 400, 4, "", 10, 10, 10],
        ],
    )
    _write_csv(
        tmp_path,
        "olist_sellers_dataset.csv",
        ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"],
        [["s1", 3000, "sao paulo", "SP"], ["s2", 4000, "rio de janeiro", "RJ"]],
    )
    _write_csv(
        tmp_path,
        "product_category_name_translation.csv",
        ["product_category_name", "product_category_name_english"],
        [["livros", "books"], ["eletronicos", "electronics"], ["brinquedos", "toys"]],
    )
    _write_csv(
        tmp_path,
        "olist_geolocation_dataset.csv",
        ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state"],
        [[1000, -23.5, -46.6, "sao paulo", "SP"], [2000, -22.9, -43.2, "rio de janeiro", "RJ"]],
    )
    return tmp_path


def _load(data_dir: Path):
    load_dataset = importlib.import_module("refactor_next.backend.analytics").load_dataset
    return load_dataset(INTERFACE, {"data_dir": str(data_dir)})


def _aggregate(ds, *, group_by=(), metrics=("order_count",), filters=None, time_range=None, sort=None, limit=None):
    arguments = {"group_by": list(group_by), "metrics": list(metrics)}
    if filters is not None:
        arguments["filters"] = filters
    if time_range is not None:
        arguments["time_range"] = time_range
    if sort is not None:
        arguments["sort"] = sort
    if limit is not None:
        arguments["limit"] = limit
    result = ds.execute("aggregate", arguments)
    assert result["success"], result
    return result


def test_standalone_loader_exposes_only_two_exploration_tools_and_cleans_modules(olist_csvs):
    before = set(sys.modules)
    ds = _load(olist_csvs)
    added = {name for name in set(sys.modules) - before if name.startswith("trusted_dataset_")}
    try:
        assert [definition["name"] for definition in ds.definitions] == ["aggregate", "compare_segments", "distribution", "relationship", "compare_periods"]
        assert len(added) == 10  # interface plus nine file-loaded sibling modules
        assert ds.description["default_scope"] == {"order_status": "delivered"}
    finally:
        ds.close()
    assert not added.intersection(sys.modules)


def test_descriptor_has_categorized_registry_and_canonical_grains(olist_csvs):
    ds = _load(olist_csvs)
    try:
        description = ds.description
        assert set(description["dimensions"]) == {"temporal", "customer", "product", "seller", "payment", "order"}
        assert set(description["metrics"]) == {"volume", "value", "reviews", "delivery", "product_logistics", "freight"}
        assert {resource["name"]: resource["row_count"] for resource in description["resources"]} == {
            "order_grain": 6,
            "item_grain": 9,
            "customer_grain": 5,
            "seller_order_grain": 8,
            "payment_grain": 9,
        }
        assert {resource["name"]: resource["row_count"] for resource in description["raw_resources"]} == {
            "raw_orders": 6, "raw_items": 9, "raw_payments": 9, "raw_reviews": 7,
            "raw_customers": 6, "raw_products": 4, "raw_sellers": 2,
            "raw_translations": 3, "raw_geolocation": 2,
        }
        product_fields = {entry["field"]: entry for entry in description["dimensions"]["product"]}
        assert product_fields["product_weight_g"]["groupable"] is False
        assert product_fields["product_category"]["groupable"] is True
        customer_fields = {entry["field"]: entry for entry in description["dimensions"]["customer"]}
        seller_fields = {entry["field"]: entry for entry in description["dimensions"]["seller"]}
        assert customer_fields["customer_zip_code_prefix"]["groupable"] is True
        assert seller_fields["seller_zip_code_prefix"]["groupable"] is True
        assert description["validation"]["raw_delivered_order_count"] == 5
        assert description["validation"]["order_grain_delivered_revenue"] == 650.0
    finally:
        ds.close()


def test_global_metrics_use_correct_grains_and_ratio_denominators(olist_csvs):
    ds = _load(olist_csvs)
    try:
        row = {}
        for metrics in (
            ("order_count", "item_count", "unique_customer_count", "revenue"),
            ("freight_value", "total_order_value", "avg_order_value", "avg_item_price"),
            ("avg_review_score", "review_comment_ratio", "low_score_ratio", "one_star_ratio"),
            ("five_star_ratio",),
        ):
            row.update(_aggregate(ds, metrics=metrics)["rows"][0])
        assert row["order_count"] == 5
        assert row["item_count"] == 8
        assert row["unique_customer_count"] == 4
        assert row["revenue"] == 650.0
        assert row["freight_value"] == 90.0
        assert row["total_order_value"] == 740.0
        assert row["avg_order_value"] == 130.0
        assert row["avg_item_price"] == 81.25
        assert row["avg_review_score"] == 3.0
        assert row["review_comment_ratio"] == 0.5
        assert row["low_score_ratio"] == 0.5
        assert row["one_star_ratio"] == 0.5
        assert row["five_star_ratio"] == 0.5
    finally:
        ds.close()


def test_delivery_metrics_use_only_eligible_dates(olist_csvs):
    ds = _load(olist_csvs)
    try:
        row = _aggregate(
            ds,
            metrics=("avg_delivery_days", "avg_approval_days", "avg_dispatch_days", "avg_transit_days"),
        )["rows"][0]
        row.update(_aggregate(ds, metrics=("late_ratio", "avg_late_days"))["rows"][0])
        assert row == pytest.approx({
            "avg_delivery_days": 6.2,
            "avg_approval_days": 0.6,
            "avg_dispatch_days": 1.5,
            "avg_transit_days": 5.25,
            "late_ratio": 0.5,
            "avg_late_days": 2.0,
        })
    finally:
        ds.close()


def test_product_logistics_metrics_use_kg_and_zero_denominator_is_null(olist_csvs):
    ds = _load(olist_csvs)
    try:
        row = _aggregate(
            ds,
            metrics=("avg_product_weight", "avg_product_volume", "avg_freight_per_item", "avg_freight_ratio"),
        )["rows"][0]
        assert row["avg_product_weight"] == pytest.approx(8.5 / 7.0)
        assert row["avg_product_volume"] == pytest.approx(1500.0)
        assert row["avg_freight_per_item"] == pytest.approx(11.25)
        assert row["avg_freight_ratio"] == pytest.approx(0.12467532467532467)
        assert ds.description["metric_index"]["avg_product_weight"]["unit"] == "kg"
        assert "NULL" in ds.description["metric_index"]["avg_freight_ratio"]["missing_strategy"]
    finally:
        ds.close()


def test_default_delivered_scope_can_be_overridden_by_explicit_status_filter(olist_csvs):
    ds = _load(olist_csvs)
    try:
        delivered = _aggregate(ds, group_by=("order_status",), metrics=("order_count", "revenue"))
        assert delivered["rows"] == [{"order_status": "delivered", "order_count": 5, "revenue": 650.0}]
        canceled = _aggregate(
            ds,
            metrics=("order_count", "revenue"),
            filters=[{"field": "order_status", "op": "eq", "value": "canceled"}],
        )
        assert canceled["rows"] == [{"order_count": 1, "revenue": 999.0}]
    finally:
        ds.close()


def test_weekly_monthly_state_category_and_multi_metric_queries(olist_csvs):
    ds = _load(olist_csvs)
    try:
        weekly = _aggregate(
            ds,
            group_by=("order_week",),
            metrics=("order_count", "revenue", "avg_review_score", "late_ratio"),
            time_range={"field": "order_date", "start": "2017-10-01", "end": "2018-04-01"},
            sort={"field": "order_week", "direction": "asc"},
        )
        assert weekly["rows"] == [
            {"order_week": "2017-10-02", "order_count": 1, "revenue": 150.0, "avg_review_score": 1.0, "late_ratio": 1.0},
            {"order_week": "2017-11-06", "order_count": 1, "revenue": 200.0, "avg_review_score": 5.0, "late_ratio": 0.0},
            {"order_week": "2018-01-08", "order_count": 1, "revenue": 80.0, "avg_review_score": None, "late_ratio": None},
            {"order_week": "2018-02-05", "order_count": 1, "revenue": 120.0, "avg_review_score": 1.0, "late_ratio": 1.0},
            {"order_week": "2018-03-12", "order_count": 1, "revenue": 100.0, "avg_review_score": 5.0, "late_ratio": 0.0},
        ]
        monthly = _aggregate(ds, group_by=("order_month",), metrics=("order_count",), sort={"field": "order_month", "direction": "asc"})
        assert [row["order_month"] for row in monthly["rows"]] == ["2017-10-01", "2017-11-01", "2018-01-01", "2018-02-01", "2018-03-01"]
        sp_books = _aggregate(
            ds,
            group_by=("product_category",),
            metrics=("order_count", "item_count", "revenue"),
            filters=[{"field": "customer_state", "op": "eq", "value": "SP"}],
            sort={"field": "product_category", "direction": "asc"},
        )
        assert sp_books["rows"] == [
            {"product_category": "books", "order_count": 2, "item_count": 2, "revenue": 300.0},
            {"product_category": "electronics", "order_count": 1, "item_count": 1, "revenue": 50.0},
            {"product_category": "toys", "order_count": 1, "item_count": 2, "revenue": 80.0},
        ]
    finally:
        ds.close()


def test_task_a_sp_weekly_quality_and_delivery_metrics(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = _aggregate(
            ds,
            group_by=("order_week",),
            metrics=("order_count", "low_score_ratio", "avg_delivery_days", "late_ratio"),
            filters=[{"field": "customer_state", "op": "eq", "value": "SP"}],
            time_range={"field": "order_date", "start": "2017-10-01", "end": "2018-04-01"},
            sort={"field": "order_week", "direction": "asc"},
        )
        assert result["rows"] == [
            {"order_week": "2017-10-02", "order_count": 1, "low_score_ratio": 1.0, "avg_delivery_days": 8.0, "late_ratio": 1.0},
            {"order_week": "2017-11-06", "order_count": 1, "low_score_ratio": 0.0, "avg_delivery_days": 5.0, "late_ratio": 0.0},
            {"order_week": "2018-01-08", "order_count": 1, "low_score_ratio": None, "avg_delivery_days": 2.0, "late_ratio": None},
        ]
    finally:
        ds.close()


def test_seller_and_payment_grouping_do_not_multiply_orders(olist_csvs):
    ds = _load(olist_csvs)
    try:
        seller = _aggregate(ds, group_by=("seller_id",), metrics=("order_count", "item_count", "revenue"), sort={"field": "seller_id", "direction": "asc"})
        assert seller["rows"] == [
            {"seller_id": "s1", "order_count": 5, "item_count": 6, "revenue": 540.0},
            {"seller_id": "s2", "order_count": 2, "item_count": 2, "revenue": 110.0},
        ]
        payment = _aggregate(ds, group_by=("payment_type",), metrics=("order_count", "revenue"), sort={"field": "payment_type", "direction": "asc"})
        assert payment["rows"] == [
            {"payment_type": "boleto", "order_count": 1, "revenue": 200.0},
            {"payment_type": "credit_card", "order_count": 2, "revenue": 250.0},
            {"payment_type": "mixed", "order_count": 1, "revenue": 80.0},
            {"payment_type": "voucher", "order_count": 1, "revenue": 120.0},
        ]
    finally:
        ds.close()


def test_compare_segments_supports_task_b_direct_dimension_objects(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("compare_segments", {
            "segments": [
                {"label": "RJ books", "customer_state": "RJ", "product_category": "books"},
                {"label": "RJ electronics", "customer_state": "RJ", "product_category": "electronics"},
            ],
            "metrics": ["order_count", "item_count", "revenue", "avg_review_score"],
        })
        assert result["success"], result
        assert result["rows"] == [
            {"segment": "RJ books", "order_count": 2, "item_count": 2, "revenue": 160.0, "avg_review_score": 3.0},
            {"segment": "RJ electronics", "order_count": 1, "item_count": 1, "revenue": 60.0, "avg_review_score": 5.0},
        ]
    finally:
        ds.close()


def test_compare_segments_preserves_an_empty_requested_segment(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("compare_segments", {
            "segments": [
                {"label": "RJ books", "customer_state": "RJ", "product_category": "books"},
                {"label": "RJ missing", "customer_state": "RJ", "product_category": "not-a-category"},
            ],
            "metrics": ["order_count", "item_count", "revenue", "avg_review_score"],
        })
        assert result["success"], result
        assert result["rows"][1] == {
            "segment": "RJ missing", "order_count": 0, "item_count": 0,
            "revenue": 0.0, "avg_review_score": None,
        }
    finally:
        ds.close()


def test_compare_segments_parameter_order_across_scope_filters_time_and_segments(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute(
            "compare_segments",
            {
                "segments": [
                    {"label": "RJ books", "product_category": "books"},
                    {"label": "RJ electronics", "product_category": "electronics"},
                ],
                "metrics": ["order_count", "revenue"],
                "filters": [{"field": "payment_type", "op": "eq", "value": "credit_card"}],
                "time_range": {"field": "order_date", "start": "2018-03-01", "end": "2018-04-01"},
            },
            [{"field": "customer_state", "op": "eq", "value": "RJ"}],
        )
        assert result["success"], result
        assert result["rows"] == [
            {"segment": "RJ books", "order_count": 1, "revenue": 40.0},
            {"segment": "RJ electronics", "order_count": 1, "revenue": 60.0},
        ]
    finally:
        ds.close()


def test_validation_rejects_unregistered_fields_bad_sort_and_one_segment(olist_csvs):
    ds = _load(olist_csvs)
    try:
        assert not ds.execute("aggregate", {"group_by": ["product_id"], "metrics": ["revenue"]})["success"]
        assert not ds.execute("aggregate", {"group_by": ["customer_state"], "metrics": ["revenue"], "sort": {"field": "item_count", "direction": "desc"}})["success"]
        assert not ds.execute("compare_segments", {"segments": [{"customer_state": "RJ"}], "metrics": ["revenue"]})["success"]
        assert ds.execute("aggregate", {"group_by": ["customer_state", "order_month"], "metrics": ["revenue"]})["success"]
        assert not ds.execute("aggregate", {"group_by": [], "metrics": ["order_count", "item_count", "revenue", "freight_value", "avg_order_value"]})["success"]
        injection = _aggregate(ds, metrics=("order_count",), filters=[{"field": "customer_state", "op": "eq", "value": "RJ' OR 1=1 --"}])
        assert injection["rows"] == [{"order_count": 0}]
    finally:
        ds.close()


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        ({"field": "purchase_hour", "op": "gt", "value": 13}, 1),
        ({"field": "purchase_hour", "op": "lt", "value": 11}, 1),
        ({"field": "customer_state", "op": "neq", "value": "SP"}, 2),
        ({"field": "purchase_hour", "op": "gte", "value": 13}, 2),
        ({"field": "purchase_hour", "op": "lte", "value": 11}, 2),
        ({"field": "customer_city", "op": "is_null"}, 1),
        ({"field": "customer_state", "op": "in", "value": ["SP", "RJ"]}, 5),
        ({"field": "order_date", "op": "between", "value": ["2017-11-06", "2018-01-08"]}, 2),
    ],
)
def test_extended_filters_are_parameter_bound_and_between_is_inclusive(olist_csvs, condition, expected):
    ds = _load(olist_csvs)
    try:
        result = _aggregate(ds, metrics=("order_count",), filters=[condition])
        assert result["rows"] == [{"order_count": expected}]
    finally:
        ds.close()


def test_result_metadata_is_complete_for_dimensions_and_metrics(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = _aggregate(ds, group_by=("customer_state",), metrics=("revenue",))
        assert set(result["columns"]["customer_state"]) >= {"type", "label", "description"}
        assert set(result["columns"]["revenue"]) >= {"type", "label", "unit", "description"}
    finally:
        ds.close()


def test_aggregate_description_matches_one_group_limit(olist_csvs):
    ds = _load(olist_csvs)
    try:
        aggregate = next(definition for definition in ds.definitions if definition["name"] == "aggregate")
        assert "zero to two" in aggregate["description"]
        assert "three" not in aggregate["description"]
    finally:
        ds.close()


def test_direct_interface_documents_connection_for_canonical_diagnostics(olist_csvs):
    module_name = "test_olist_interface_direct"
    spec = importlib.util.spec_from_file_location(module_name, INTERFACE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        adapter = module.open_dataset({"data_dir": str(olist_csvs)})
        try:
            counts = {
                table: adapter.connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in ("order_grain", "item_grain", "customer_grain", "seller_order_grain", "payment_grain")
            }
            assert counts == {"order_grain": 6, "item_grain": 9, "customer_grain": 5, "seller_order_grain": 8, "payment_grain": 9}
            raw_counts = {
                table: adapter.connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in (
                    "raw_orders", "raw_items", "raw_payments", "raw_reviews", "raw_customers",
                    "raw_products", "raw_sellers", "raw_translations", "raw_geolocation",
                )
            }
            assert raw_counts == {
                "raw_orders": 6, "raw_items": 9, "raw_payments": 9, "raw_reviews": 7,
                "raw_customers": 6, "raw_products": 4, "raw_sellers": 2,
                "raw_translations": 3, "raw_geolocation": 2,
            }
            payment = adapter.connection.execute(
                "SELECT payment_sequential, payment_type, payment_installments, payment_value, "
                "order_status, order_date, customer_state, customer_zip_code_prefix FROM payment_grain "
                "WHERE order_id = 'o1' ORDER BY payment_sequential LIMIT 1"
            ).fetchone()
            assert payment == (1, "credit_card", 2, 100.0, "delivered", date(2017, 10, 2), "SP", 1000)
            order = adapter.connection.execute(
                "SELECT customer_unique_id, customer_zip_code_prefix, item_count, revenue, freight_value, "
                "payment_type, review_score, promise_window_days, late_days "
                "FROM order_grain WHERE order_id = 'o1'"
            ).fetchone()
            assert order == ("u1", 1000, 2, 150.0, 15.0, "credit_card", 1.0, 7.0, 1.0)
            on_time = adapter.connection.execute(
                "SELECT promise_window_days, late_days FROM order_grain WHERE order_id = 'o2'"
            ).fetchone()
            assert on_time == (9.0, 0.0)
            impossible_promise = adapter.connection.execute(
                "SELECT promise_window_days, is_late, late_days FROM order_grain WHERE order_id = 'o3'"
            ).fetchone()
            assert impossible_promise == (None, None, None)
            canonical_review = adapter.connection.execute(
                "SELECT review_id, review_score FROM order_grain WHERE order_id = 'o2'"
            ).fetchone()
            assert canonical_review == ("r3", 5.0)
            item = adapter.connection.execute(
                "SELECT customer_zip_code_prefix, seller_zip_code_prefix, promise_window_days, late_days "
                "FROM item_grain WHERE order_id = 'o1' AND order_item_id = 1"
            ).fetchone()
            assert item == (1000, 3000, 7.0, 1.0)
            seller_order = adapter.connection.execute(
                "SELECT customer_zip_code_prefix, seller_zip_code_prefix, promise_window_days, late_days "
                "FROM seller_order_grain WHERE order_id = 'o1' AND seller_id = 's1'"
            ).fetchone()
            assert seller_order == (1000, 3000, 7.0, 1.0)
        finally:
            adapter.close()
    finally:
        sys.modules.pop(module_name, None)
