"""Source manifest and semantic dimensions for the Olist adapter."""

FILES = {
    "orders": "olist_orders_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "translations": "product_category_name_translation.csv",
    "geolocation": "olist_geolocation_dataset.csv",
}


def _dimension(field, label, kind, description, grain, *, groupable=True, column=None):
    return {
        "field": field,
        "label": label,
        "type": kind,
        "description": description,
        "grain": grain,
        "groupable": groupable,
        "column": column or field,
    }


DIMENSIONS = {
    "temporal": [
        _dimension("order_date", "Purchase date", "temporal", "Calendar date of purchase.", "order"),
        _dimension("order_week", "Purchase week", "temporal", "Monday starting the purchase week.", "order"),
        _dimension("order_month", "Purchase month", "temporal", "First day of the purchase month.", "order"),
        _dimension("order_quarter", "Purchase quarter", "temporal", "First day of the purchase quarter.", "order"),
        _dimension("weekday", "Purchase weekday", "ordinal", "English weekday name, Monday through Sunday.", "order"),
        _dimension("purchase_hour", "Purchase hour", "ordinal", "Hour of day from 0 through 23.", "order"),
        # Short aliases make the vocabulary natural without breaking the original order_* names.
        _dimension("date", "Purchase date", "temporal", "Alias of order_date.", "order", column="order_date"),
        _dimension("week", "Purchase week", "temporal", "Alias of order_week.", "order", column="order_week"),
        _dimension("month", "Purchase month", "temporal", "Alias of order_month.", "order", column="order_month"),
        _dimension("quarter", "Purchase quarter", "temporal", "Alias of order_quarter.", "order", column="order_quarter"),
    ],
    "customer": [
        _dimension("customer_state", "Customer state", "nominal", "Customer delivery state code.", "order"),
        _dimension("customer_city", "Customer city", "nominal", "Customer delivery city.", "order"),
        _dimension("customer_zip_code_prefix", "Customer ZIP prefix", "nominal", "Customer delivery ZIP-code prefix.", "order"),
        _dimension("customer_unique_id", "Unique customer", "nominal", "Stable customer identifier across orders.", "order", groupable=False),
    ],
    "product": [
        _dimension("product_category", "Product category", "nominal", "English category when translated, otherwise the raw category.", "item"),
        _dimension("product_id", "Product ID", "nominal", "Raw product identifier; retained for lineage, not semantic grouping.", "item", groupable=False),
        _dimension("product_category_name", "Raw product category", "nominal", "Raw Portuguese category.", "item", groupable=False),
        _dimension("product_name_lenght", "Product name length", "quantitative", "Raw source field (original Olist spelling).", "item", groupable=False),
        _dimension("product_description_lenght", "Product description length", "quantitative", "Raw source field (original Olist spelling).", "item", groupable=False),
        _dimension("product_photos_qty", "Product photo count", "quantitative", "Raw product photo count.", "item", groupable=False),
        _dimension("product_weight_g", "Product weight (raw)", "quantitative", "Raw product weight in grams.", "item", groupable=False),
        _dimension("product_length_cm", "Product length", "quantitative", "Raw product length in centimetres.", "item", groupable=False),
        _dimension("product_height_cm", "Product height", "quantitative", "Raw product height in centimetres.", "item", groupable=False),
        _dimension("product_width_cm", "Product width", "quantitative", "Raw product width in centimetres.", "item", groupable=False),
    ],
    "seller": [
        _dimension("seller_id", "Seller", "nominal", "Seller identifier.", "item"),
        _dimension("seller_state", "Seller state", "nominal", "Seller state code.", "item"),
        _dimension("seller_city", "Seller city", "nominal", "Seller city.", "item"),
        _dimension("seller_zip_code_prefix", "Seller ZIP prefix", "nominal", "Seller ZIP-code prefix.", "item"),
    ],
    "payment": [
        _dimension("payment_type", "Payment type", "nominal", "Single order payment type; mixed when an order uses multiple types.", "order"),
        _dimension("payment_installments", "Payment installments", "ordinal", "Maximum installment count recorded for the order.", "order"),
    ],
    "order": [
        _dimension("order_status", "Order status", "nominal", "Raw Olist order status; all statuses are retained.", "order"),
        _dimension("order_id", "Order ID", "nominal", "Raw order identifier retained for lineage.", "order", groupable=False),
        _dimension("customer_id", "Order customer ID", "nominal", "Order-scoped customer identifier.", "order", groupable=False),
        _dimension("promise_window_days", "Promise window", "quantitative", "Non-negative days from purchase to estimated delivery.", "order", groupable=False),
    ],
}

DIMENSION_INDEX = {
    entry["field"]: {**entry, "category": category}
    for category, entries in DIMENSIONS.items()
    for entry in entries
}
GROUPABLE_DIMENSIONS = {
    field: entry for field, entry in DIMENSION_INDEX.items() if entry["groupable"]
}

# The analytical variable namespace is separate from aggregate metrics.
OBSERVATION_FIELDS = {
    "order": {"delivery_days": "days", "approval_days": "days", "dispatch_days": "days",
              "transit_days": "days", "review_score": "points", "is_late": "flag"},
    "item": {"price": "BRL", "freight_value": "BRL", "product_weight_kg": "kg",
             "product_volume_cm3": "cm3", "freight_ratio": "ratio"},
}
FIELD_INDEX = {
    field: {**entry, "unit": None, "filterable": entry["groupable"],
            "value_type": "number" if field in {"purchase_hour", "payment_installments", "customer_zip_code_prefix", "seller_zip_code_prefix"} else "string",
            "allowed_ops": ["eq", "neq", "gt", "gte", "lt", "lte", "in", "between", "is_null", "is_not_null"],
            "observation_units": ["order", "item"] if entry["grain"] == "order" else ["item"]}
    for field, entry in DIMENSION_INDEX.items()
}
for _unit, _fields in OBSERVATION_FIELDS.items():
    for _field, _measure_unit in _fields.items():
        FIELD_INDEX[_field] = {"field": _field, "label": _field.replace("_", " ").title(),
                                "type": "quantitative", "grain": _unit, "unit": _measure_unit,
                                "category": "product" if _unit == "item" else "order",
                                "groupable": False, "filterable": True, "column": _field,
                                "allowed_ops": ["eq", "neq", "gt", "gte", "lt", "lte", "in", "between", "is_null", "is_not_null"],
                                "observation_units": [_unit]}
