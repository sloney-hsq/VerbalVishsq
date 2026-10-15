"""Continuous exploratory analytics over the nine-file Olist dataset."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import math
from pathlib import Path
import sys

import duckdb


SEMANTIC_VERSION = b"olist-exploration-v5-valid-estimate-lateness"


def _load_sibling(stem):
    """Load a sibling safely when this file itself has no package context."""
    path = Path(__file__).with_name(stem + ".py")
    name = f"{__name__}_{stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Unable to load Olist module: {stem}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _file_digest(paths):
    digest = hashlib.sha256(SEMANTIC_VERSION)
    for name, path in sorted(paths.items()):
        digest.update(name.encode("utf-8"))
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()[:16]


def _duration(start, end, condition="TRUE"):
    return (f"CASE WHEN {condition} AND {start} IS NOT NULL AND {end} IS NOT NULL "
            f"AND {end} >= {start} THEN epoch({end} - {start}) / 86400.0 END")


class Olist:
    """Read-only, in-memory snapshot with documented canonical DuckDB grains."""

    def __init__(self, config):
        self._closed = False
        self._module_names = []
        self.con = None
        try:
            self.schema = self._load("schema")
            self.metrics = self._load("metrics")
            self.queries = self._load("queries")
            if not config.get("data_dir"):
                raise ValueError("Olist requires configured data_dir")
            directory = Path(config["data_dir"]).resolve(strict=True)
            paths = {name: (directory / filename).resolve(strict=True) for name, filename in self.schema.FILES.items()}
            self.version = "olist-5-" + _file_digest(paths)
            self.con = duckdb.connect(":memory:")
            for name, path in paths.items():
                self.con.execute(
                    f'CREATE TABLE "raw_{name}" AS SELECT * FROM read_csv_auto(?, header=true, sample_size=-1)',
                    [str(path)],
                )
            self._create_grains()
            self._validate_grains()
        except BaseException:
            if self.con is not None:
                self.con.close()
            self._unload_modules()
            raise

    def _load(self, stem):
        module = _load_sibling(stem)
        self._module_names.append(module.__name__)
        return module

    def _unload_modules(self):
        for name in reversed(self._module_names):
            sys.modules.pop(name, None)
        self._module_names.clear()

    def _create_grains(self):
        delivery = _duration("order_purchase_timestamp", "order_delivered_customer_date", "order_status = 'delivered'")
        approval = _duration("order_purchase_timestamp", "order_approved_at")
        dispatch = _duration("order_approved_at", "order_delivered_carrier_date")
        transit = _duration("order_delivered_carrier_date", "order_delivered_customer_date", "order_status = 'delivered'")
        promise = _duration("order_purchase_timestamp", "order_estimated_delivery_date")
        self.con.execute("""
            CREATE TABLE review_order AS
            SELECT order_id, review_id, TRY_CAST(review_score AS DOUBLE)::DOUBLE AS review_score,
                   CAST(review_comment_title AS VARCHAR) AS review_comment_title,
                   CAST(review_comment_message AS VARCHAR) AS review_comment_message,
                   TRY_CAST(review_creation_date AS TIMESTAMP) AS review_creation_date,
                   TRY_CAST(review_answer_timestamp AS TIMESTAMP) AS review_answer_timestamp,
                   CASE WHEN NULLIF(TRIM(COALESCE(CAST(review_comment_title AS VARCHAR), '')), '') IS NOT NULL
                                  OR NULLIF(TRIM(COALESCE(CAST(review_comment_message AS VARCHAR), '')), '') IS NOT NULL
                        THEN 1 ELSE 0 END::INTEGER AS review_comment_present,
                   1::BIGINT AS review_count
            FROM raw_reviews
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY order_id
                ORDER BY TRY_CAST(review_creation_date AS TIMESTAMP) DESC NULLS LAST, review_id DESC
            ) = 1
        """)
        self.con.execute("""
            CREATE TABLE payment_order AS
            SELECT order_id,
                   CASE COUNT(DISTINCT payment_type) WHEN 0 THEN NULL WHEN 1 THEN MIN(payment_type) ELSE 'mixed' END AS payment_type,
                   MAX(TRY_CAST(payment_installments AS INTEGER)) AS payment_installments,
                   SUM(TRY_CAST(payment_value AS DOUBLE))::DOUBLE AS payment_value,
                   COUNT(*)::BIGINT AS payment_record_count
            FROM raw_payments GROUP BY order_id
        """)
        self.con.execute("""
            CREATE TABLE item_enriched AS
            SELECT i.order_id, TRY_CAST(i.order_item_id AS INTEGER) AS order_item_id,
                   i.product_id, i.seller_id, TRY_CAST(i.shipping_limit_date AS TIMESTAMP) AS shipping_limit_date,
                   TRY_CAST(i.price AS DOUBLE) AS price, TRY_CAST(i.freight_value AS DOUBLE) AS freight_value,
                   CASE WHEN i.price IS NULL AND i.freight_value IS NULL THEN NULL
                        ELSE COALESCE(TRY_CAST(i.price AS DOUBLE), 0) + COALESCE(TRY_CAST(i.freight_value AS DOUBLE), 0) END::DOUBLE AS total_item_value,
                   CASE WHEN TRY_CAST(i.price AS DOUBLE) IS NOT NULL AND TRY_CAST(i.freight_value AS DOUBLE) IS NOT NULL
                                  AND TRY_CAST(i.price AS DOUBLE) + TRY_CAST(i.freight_value AS DOUBLE) > 0
                        THEN TRY_CAST(i.freight_value AS DOUBLE) / (TRY_CAST(i.price AS DOUBLE) + TRY_CAST(i.freight_value AS DOUBLE)) END::DOUBLE AS freight_ratio,
                   COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS product_category,
                   p.product_category_name, p.product_name_lenght, p.product_description_lenght,
                   p.product_photos_qty, p.product_weight_g, p.product_length_cm, p.product_height_cm, p.product_width_cm,
                   CASE WHEN TRY_CAST(p.product_weight_g AS DOUBLE) > 0 THEN TRY_CAST(p.product_weight_g AS DOUBLE) / 1000.0 END::DOUBLE AS product_weight_kg,
                   CASE WHEN TRY_CAST(p.product_length_cm AS DOUBLE) > 0 AND TRY_CAST(p.product_height_cm AS DOUBLE) > 0
                                  AND TRY_CAST(p.product_width_cm AS DOUBLE) > 0
                        THEN TRY_CAST(p.product_length_cm AS DOUBLE) * TRY_CAST(p.product_height_cm AS DOUBLE) *
                             TRY_CAST(p.product_width_cm AS DOUBLE) END::DOUBLE AS product_volume_cm3,
                   s.seller_city, s.seller_state, s.seller_zip_code_prefix
            FROM raw_items i
            LEFT JOIN raw_products p ON i.product_id = p.product_id
            LEFT JOIN raw_translations t ON p.product_category_name = t.product_category_name
            LEFT JOIN raw_sellers s ON i.seller_id = s.seller_id
        """)
        self.con.execute("""
            CREATE TABLE item_order_agg AS
            SELECT order_id, COUNT(*)::BIGINT AS item_count, COUNT(price)::BIGINT AS price_count,
                   SUM(price)::DOUBLE AS revenue, COUNT(freight_value)::BIGINT AS freight_count,
                   SUM(freight_value)::DOUBLE AS freight_value, SUM(total_item_value)::DOUBLE AS total_order_value,
                   SUM(product_weight_kg)::DOUBLE AS product_weight_sum, COUNT(product_weight_kg)::BIGINT AS product_weight_count,
                   SUM(product_volume_cm3)::DOUBLE AS product_volume_sum, COUNT(product_volume_cm3)::BIGINT AS product_volume_count,
                   SUM(freight_ratio)::DOUBLE AS freight_ratio_sum, COUNT(freight_ratio)::BIGINT AS freight_ratio_count
            FROM item_enriched GROUP BY order_id
        """)
        self.con.execute(f"""
            CREATE TABLE order_grain AS
            WITH typed AS (
                SELECT o.order_id, o.customer_id, o.order_status,
                       TRY_CAST(o.order_purchase_timestamp AS TIMESTAMP) AS order_purchase_timestamp,
                       TRY_CAST(o.order_approved_at AS TIMESTAMP) AS order_approved_at,
                       TRY_CAST(o.order_delivered_carrier_date AS TIMESTAMP) AS order_delivered_carrier_date,
                       TRY_CAST(o.order_delivered_customer_date AS TIMESTAMP) AS order_delivered_customer_date,
                       TRY_CAST(o.order_estimated_delivery_date AS TIMESTAMP) AS order_estimated_delivery_date,
                       c.customer_unique_id, c.customer_city, c.customer_state, c.customer_zip_code_prefix
                FROM raw_orders o LEFT JOIN raw_customers c ON o.customer_id = c.customer_id
            )
            SELECT typed.*, CAST(order_purchase_timestamp AS DATE) AS order_date,
                   CAST(date_trunc('week', order_purchase_timestamp) AS DATE) AS order_week,
                   CAST(date_trunc('month', order_purchase_timestamp) AS DATE) AS order_month,
                   CAST(date_trunc('quarter', order_purchase_timestamp) AS DATE) AS order_quarter,
                   strftime(order_purchase_timestamp, '%A') AS weekday,
                   date_part('hour', order_purchase_timestamp)::INTEGER AS purchase_hour,
                   COALESCE(a.item_count, 0)::BIGINT AS item_count, COALESCE(a.price_count, 0)::BIGINT AS price_count,
                   COALESCE(a.revenue, 0)::DOUBLE AS revenue, COALESCE(a.freight_count, 0)::BIGINT AS freight_count,
                   COALESCE(a.freight_value, 0)::DOUBLE AS freight_value, COALESCE(a.total_order_value, 0)::DOUBLE AS total_order_value,
                   a.product_weight_sum, COALESCE(a.product_weight_count, 0)::BIGINT AS product_weight_count,
                   a.product_volume_sum, COALESCE(a.product_volume_count, 0)::BIGINT AS product_volume_count,
                   a.freight_ratio_sum, COALESCE(a.freight_ratio_count, 0)::BIGINT AS freight_ratio_count,
                   r.review_id, r.review_score, r.review_comment_title, r.review_comment_message,
                   r.review_creation_date, r.review_answer_timestamp, r.review_comment_present,
                   COALESCE(r.review_count, 0)::BIGINT AS review_count,
                   p.payment_type, p.payment_installments, p.payment_value,
                   COALESCE(p.payment_record_count, 0)::BIGINT AS payment_record_count,
                   ({delivery})::DOUBLE AS delivery_days, ({approval})::DOUBLE AS approval_days,
                   ({dispatch})::DOUBLE AS dispatch_days, ({transit})::DOUBLE AS transit_days,
                   ({promise})::DOUBLE AS promise_window_days,
                   CASE WHEN order_status = 'delivered' AND order_delivered_customer_date IS NOT NULL
                                  AND order_estimated_delivery_date IS NOT NULL AND order_delivered_customer_date >= order_purchase_timestamp
                                  AND order_estimated_delivery_date >= order_purchase_timestamp
                        THEN (order_delivered_customer_date > order_estimated_delivery_date)::INTEGER END AS is_late,
                   CASE WHEN order_status = 'delivered' AND order_delivered_customer_date IS NOT NULL
                                  AND order_estimated_delivery_date IS NOT NULL
                                  AND order_delivered_customer_date >= order_purchase_timestamp
                                  AND order_estimated_delivery_date >= order_purchase_timestamp
                        THEN GREATEST(epoch(order_delivered_customer_date - order_estimated_delivery_date) / 86400.0, 0)
                   END::DOUBLE AS late_days
            FROM typed LEFT JOIN item_order_agg a USING (order_id)
            LEFT JOIN review_order r USING (order_id) LEFT JOIN payment_order p USING (order_id)
        """)
        self.con.execute("""
            CREATE TABLE payment_grain AS
            SELECT p.order_id,
                   TRY_CAST(p.payment_sequential AS INTEGER) AS payment_sequential,
                   CAST(p.payment_type AS VARCHAR) AS payment_type,
                   TRY_CAST(p.payment_installments AS INTEGER) AS payment_installments,
                   TRY_CAST(p.payment_value AS DOUBLE)::DOUBLE AS payment_value,
                   o.order_status, o.order_date, o.order_purchase_timestamp,
                   o.customer_id, o.customer_unique_id, o.customer_state, o.customer_city,
                   o.customer_zip_code_prefix
            FROM raw_payments p
            LEFT JOIN order_grain o USING (order_id)
        """)
        self.con.execute("""
            CREATE TABLE item_grain AS
            SELECT i.*, o.customer_id, o.customer_unique_id, o.customer_city, o.customer_state,
                   o.customer_zip_code_prefix, o.order_status,
                   o.order_purchase_timestamp, o.order_approved_at, o.order_delivered_carrier_date,
                   o.order_delivered_customer_date, o.order_estimated_delivery_date,
                   o.order_date, o.order_week, o.order_month, o.order_quarter, o.weekday, o.purchase_hour,
                   o.review_id, o.review_score, o.review_comment_title, o.review_comment_message,
                   o.review_creation_date, o.review_answer_timestamp, o.review_comment_present, o.review_count,
                   o.payment_type, o.payment_installments,
                   o.payment_value, o.payment_record_count, o.delivery_days, o.approval_days, o.dispatch_days,
                   o.transit_days, o.promise_window_days, o.is_late, o.late_days
            FROM item_enriched i JOIN order_grain o USING (order_id)
        """)
        self.con.execute("""
            CREATE TABLE customer_grain AS
            SELECT customer_unique_id, arg_max(customer_id, order_purchase_timestamp) AS latest_customer_id,
                   arg_max(customer_city, order_purchase_timestamp) AS customer_city,
                   arg_max(customer_state, order_purchase_timestamp) AS customer_state,
                   arg_max(customer_zip_code_prefix, order_purchase_timestamp) AS customer_zip_code_prefix,
                   MIN(order_purchase_timestamp) AS first_purchase_timestamp,
                   MAX(order_purchase_timestamp) AS latest_purchase_timestamp,
                   COUNT(*)::BIGINT AS order_count, SUM(item_count)::BIGINT AS item_count,
                   SUM(revenue)::DOUBLE AS revenue, SUM(freight_value)::DOUBLE AS freight_value,
                   SUM(total_order_value)::DOUBLE AS total_order_value
            FROM order_grain WHERE customer_unique_id IS NOT NULL GROUP BY customer_unique_id
        """)
        self.con.execute("""
            CREATE TABLE seller_order_grain AS
            SELECT seller_id, order_id, ANY_VALUE(seller_state) AS seller_state, ANY_VALUE(seller_city) AS seller_city,
                   ANY_VALUE(seller_zip_code_prefix) AS seller_zip_code_prefix,
                   ANY_VALUE(customer_unique_id) AS customer_unique_id, ANY_VALUE(customer_state) AS customer_state,
                   ANY_VALUE(customer_city) AS customer_city,
                   ANY_VALUE(customer_zip_code_prefix) AS customer_zip_code_prefix,
                   ANY_VALUE(order_status) AS order_status,
                   ANY_VALUE(order_date) AS order_date, ANY_VALUE(order_week) AS order_week,
                   ANY_VALUE(order_month) AS order_month, ANY_VALUE(order_quarter) AS order_quarter,
                   ANY_VALUE(weekday) AS weekday, ANY_VALUE(purchase_hour) AS purchase_hour,
                   ANY_VALUE(payment_type) AS payment_type, ANY_VALUE(payment_installments) AS payment_installments,
                   ANY_VALUE(review_score) AS review_score, ANY_VALUE(review_count) AS review_count,
                   ANY_VALUE(review_comment_present) AS review_comment_present,
                   ANY_VALUE(delivery_days) AS delivery_days, ANY_VALUE(approval_days) AS approval_days,
                   ANY_VALUE(dispatch_days) AS dispatch_days, ANY_VALUE(transit_days) AS transit_days,
                   ANY_VALUE(promise_window_days) AS promise_window_days,
                   ANY_VALUE(is_late) AS is_late, ANY_VALUE(late_days) AS late_days,
                   COUNT(*)::BIGINT AS item_count, COUNT(price)::BIGINT AS price_count,
                   SUM(price)::DOUBLE AS revenue, COUNT(freight_value)::BIGINT AS freight_count,
                   SUM(freight_value)::DOUBLE AS freight_value, SUM(total_item_value)::DOUBLE AS total_order_value,
                   SUM(product_weight_kg)::DOUBLE AS product_weight_sum, COUNT(product_weight_kg)::BIGINT AS product_weight_count,
                   SUM(product_volume_cm3)::DOUBLE AS product_volume_sum, COUNT(product_volume_cm3)::BIGINT AS product_volume_count,
                   SUM(freight_ratio)::DOUBLE AS freight_ratio_sum, COUNT(freight_ratio)::BIGINT AS freight_ratio_count
            FROM item_grain GROUP BY seller_id, order_id
        """)

    def _validate_grains(self):
        raw = self.con.execute("""
            SELECT COUNT(DISTINCT o.order_id)::BIGINT, COALESCE(SUM(TRY_CAST(i.price AS DOUBLE)), 0)::DOUBLE,
                   COALESCE(SUM(TRY_CAST(i.freight_value AS DOUBLE)), 0)::DOUBLE
            FROM raw_orders o LEFT JOIN raw_items i USING (order_id) WHERE o.order_status = 'delivered'
        """).fetchone()
        canonical = self.con.execute("""
            SELECT COUNT(*)::BIGINT, COALESCE(SUM(revenue), 0)::DOUBLE, COALESCE(SUM(freight_value), 0)::DOUBLE
            FROM order_grain WHERE order_status = 'delivered'
        """).fetchone()
        if raw[0] != canonical[0] or not all(
            math.isclose(raw[index], canonical[index], rel_tol=1e-12, abs_tol=1e-6)
            for index in (1, 2)
        ):
            raise ValueError(f"Olist grain validation failed: raw={raw!r}, canonical={canonical!r}")
        self._validation = dict(zip(
            ("raw_delivered_order_count", "raw_delivered_revenue", "raw_delivered_freight",
             "order_grain_delivered_order_count", "order_grain_delivered_revenue", "order_grain_delivered_freight"),
            (*raw, *canonical),
        ))
        self._row_counts = {table: self.con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                            for table in ("order_grain", "item_grain", "customer_grain", "seller_order_grain", "payment_grain")}
        self._raw_row_counts = {
            "raw_" + name: self.con.execute(f'SELECT COUNT(*) FROM "raw_{name}"').fetchone()[0]
            for name in self.schema.FILES
        }

    @property
    def connection(self):
        """Documented read-only diagnostic access to the in-memory canonical snapshot."""
        if self._closed:
            raise ValueError("Olist dataset is closed")
        return self.con

    def describe(self):
        return {
            "dataset_id": "olist", "version": self.version,
            "description": (
                "Olist exploratory vocabulary over persisted order, item, customer, and seller-order grains. "
                "All raw order statuses are retained; tools default to delivered orders unless order_status is explicit. "
                "Revenue is item price without freight. Each order uses one canonical review selected by newest creation "
                "timestamp then review ID; payments aggregate safely to one order row while payment_grain preserves records. "
                "Week starts Monday; filter between is inclusive and time ranges are [start, end)."
            ),
            "default_scope": {"order_status": "delivered"},
            "dimensions": deepcopy(self.schema.DIMENSIONS),
            "dimension_index": deepcopy(self.schema.DIMENSION_INDEX),
            "metrics": deepcopy(self.metrics.METRICS),
            "metric_index": deepcopy(self.metrics.METRIC_INDEX),
            "resources": [{"name": name, "grain": {
                "order_grain": "one row per order", "item_grain": "one row per order item",
                "customer_grain": "one row per customer_unique_id", "seller_order_grain": "one row per seller and order",
                "payment_grain": "one row per payment record",
            }[name], "row_count": count} for name, count in self._row_counts.items()],
            "raw_resources": [{"name": name, "grain": "raw CSV row", "row_count": count}
                              for name, count in self._raw_row_counts.items()],
            "grains": {"order": "order_grain", "item": "item_grain", "customer": "customer_grain",
                       "seller_order": "seller_order_grain", "payment": "payment_grain"},
            "filters": {"fields": list(self.schema.GROUPABLE_DIMENSIONS),
                        "operators": ["eq", "neq", "gte", "lte", "gt", "lt", "in", "between", "is_null"],
                        "combination": "AND; values are parameter-bound; shared scope precedes tool filters."},
            "validation": deepcopy(self._validation),
        }

    def _filter_schema(self):
        return {"type": "object", "properties": {
            "field": {"type": "string", "enum": list(self.schema.GROUPABLE_DIMENSIONS)},
            "op": {"type": "string", "enum": ["eq", "neq", "gte", "lte", "gt", "lt", "in", "between", "is_null"]}, "value": {},
        }, "required": ["field", "op"], "additionalProperties": False}

    def _common_properties(self):
        return {
            "metrics": {"type": "array", "items": {"type": "string", "enum": list(self.metrics.METRIC_INDEX)},
                        "minItems": 1, "maxItems": 4, "uniqueItems": True},
            "filters": {"type": "array", "items": self._filter_schema()},
            "time_range": {"type": "object", "properties": {
                "field": {"type": "string", "enum": [entry["field"] for entry in self.schema.DIMENSIONS["temporal"]]},
                "start": {"type": "string"}, "end": {"type": "string"},
            }, "anyOf": [{"required": ["start"]}, {"required": ["end"]}], "additionalProperties": False},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
        }

    def tool_definitions(self):
        dimensions, metrics = list(self.schema.GROUPABLE_DIMENSIONS), list(self.metrics.METRIC_INDEX)
        aggregate = {"group_by": {"type": "array", "items": {"type": "string", "enum": dimensions},
                                  "minItems": 0, "maxItems": 1, "uniqueItems": True}, **self._common_properties(),
                     "sort": {"type": "object", "properties": {
                         "field": {"type": "string", "enum": [*dimensions, *metrics]},
                         "direction": {"type": "string", "enum": ["asc", "desc"]},
                     }, "required": ["field", "direction"], "additionalProperties": False}}
        scalar = {"type": ["string", "number", "integer", "boolean", "null"]}
        segment_properties = {field: scalar for field in dimensions}
        segment_properties.update({"name": {"type": "string"}, "label": {"type": "string"}})
        segment = {"type": "object", "properties": segment_properties,
                   "anyOf": [{"required": [field]} for field in dimensions], "additionalProperties": False}
        comparison = {"segments": {"type": "array", "items": segment, "minItems": 2, "maxItems": 20},
                      **self._common_properties()}
        return [
            {"name": "aggregate", "description": "Aggregate registered metrics across zero or one semantic dimension.",
             "read_only": True, "parameters": {"type": "object", "properties": aggregate,
                                                  "required": ["group_by", "metrics"], "additionalProperties": False}},
            {"name": "compare_segments", "description": "Compare direct dimension segments with common metrics and filters.",
             "read_only": True, "parameters": {"type": "object", "properties": comparison,
                                                  "required": ["segments", "metrics"], "additionalProperties": False}},
        ]

    def _columns(self, names):
        columns = {}
        for name in names:
            if name == "segment":
                columns[name] = {"type": "nominal", "label": "Segment", "description": "Requested comparison segment."}
            elif name in self.schema.DIMENSION_INDEX:
                entry = self.schema.DIMENSION_INDEX[name]
                columns[name] = {key: entry[key] for key in ("type", "label", "description", "grain")}
            else:
                entry = self.metrics.METRIC_INDEX[name]
                columns[name] = {key: entry[key] for key in ("type", "label", "description", "grain", "unit", "category")}
        return columns

    def execute(self, name, arguments, scope=None):
        if self._closed:
            raise ValueError("Olist dataset is closed")
        if scope is not None and not isinstance(scope, list):
            raise ValueError("Scope must be a list of filters")
        if name == "aggregate":
            query = self.queries.build_aggregate(arguments, scope, self.schema.DIMENSION_INDEX, self.metrics.METRIC_INDEX)
        elif name == "compare_segments":
            query = self.queries.build_segments(arguments, scope, self.schema.DIMENSION_INDEX, self.metrics.METRIC_INDEX)
        else:
            raise ValueError("Unknown Olist tool")
        sql, params, names, limit = query
        raw_rows = self.con.execute(sql, params).fetchall()
        return {"success": True, "dataset_version": self.version,
                "rows": [{field: value for field, value in zip(names, row)} for row in raw_rows[:limit]],
                "columns": self._columns(names), "truncated": len(raw_rows) > limit}

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                if self.con is not None:
                    self.con.close()
            finally:
                self._unload_modules()


def open_dataset(config):
    return Olist(config)
