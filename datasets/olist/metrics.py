"""Metric registry for the Olist adapter."""


def _metric(field, label, category, formula, denominator, missing_strategy, unit, grain):
    return {
        "field": field,
        "label": label,
        "type": "quantitative",
        "description": formula,
        "category": category,
        "formula": formula,
        "denominator": denominator,
        "missing_strategy": missing_strategy,
        "unit": unit,
        "grain": grain,
    }


METRIC_INDEX = {
    entry["field"]: entry
    for entry in [
        _metric("order_count", "Orders", "volume", "Count of distinct orders in the selected segment.", "distinct eligible orders", "No order contributes zero.", "orders", "order"),
        _metric("reviewed_order_count", "Reviewed orders", "volume", "Count of orders with a valid canonical score.", "orders with valid score", "Missing or invalid scores excluded.", "orders", "order"),
        _metric("valid_delivery_order_count", "Valid delivery orders", "volume", "Count of delivered orders with valid non-negative delivery duration.", "orders with valid duration", "Missing or negative durations excluded.", "orders", "order"),
        _metric("late_eligible_order_count", "Late eligible orders", "volume", "Count of orders with determinable lateness.", "orders with valid lateness", "Missing endpoints excluded.", "orders", "order"),
        _metric("item_count", "Items", "volume", "Count of order-item rows.", "eligible item rows", "No item contributes zero.", "items", "item"),
        _metric("unique_customer_count", "Unique customers", "volume", "Count of distinct non-null customer_unique_id values.", "distinct customer_unique_id", "Missing customer IDs are excluded.", "customers", "order"),
        _metric("revenue", "Revenue", "value", "Sum of item price; freight is excluded.", "eligible item rows", "NULL prices are excluded from the sum.", "BRL", "item"),
        _metric("freight_value", "Freight", "value", "Sum of item freight value.", "eligible item rows", "NULL freight values are excluded.", "BRL", "item"),
        _metric("total_order_value", "Total order value", "value", "Sum of item price plus freight.", "eligible item rows", "Rows missing both components are excluded.", "BRL", "item"),
        _metric("avg_order_value", "Average order value", "value", "Item revenue divided by distinct orders in the segment.", "distinct orders", "Returns NULL when there are no orders.", "BRL/order", "order"),
        _metric("avg_item_price", "Average item price", "value", "Item revenue divided by items with a non-null price.", "items with price", "Returns NULL when no item has a price.", "BRL/item", "item"),
        _metric("avg_review_score", "Average review score", "reviews", "Mean canonical review score, one selected review per order.", "reviewed orders", "Orders without a canonical non-null score are excluded; each order is weighted once per segment.", "points", "order"),
        _metric("review_comment_ratio", "Review comment ratio", "reviews", "Share of canonically reviewed orders with a non-empty title or message.", "orders with a canonical review record", "Orders without a canonical review are excluded.", "ratio", "order"),
        _metric("low_score_ratio", "Low-score ratio", "reviews", "Share of canonical reviewed-order scores at most 2.", "reviewed orders with score", "Orders without a canonical non-null score are excluded.", "ratio", "order"),
        _metric("one_star_ratio", "One-star ratio", "reviews", "Share of canonical reviewed-order scores equal to 1.", "reviewed orders with score", "Orders without a canonical non-null score are excluded.", "ratio", "order"),
        _metric("five_star_ratio", "Five-star ratio", "reviews", "Share of canonical reviewed-order scores equal to 5.", "reviewed orders with score", "Orders without a canonical non-null score are excluded.", "ratio", "order"),
        _metric("avg_delivery_days", "Average delivery days", "delivery", "Mean elapsed days from purchase to customer delivery.", "delivered orders with both endpoints and non-negative duration", "Ineligible or negative durations are NULL.", "days", "order"),
        _metric("avg_approval_days", "Average approval days", "delivery", "Mean elapsed days from purchase to approval.", "orders with both endpoints and non-negative duration", "Ineligible or negative durations are NULL.", "days", "order"),
        _metric("avg_dispatch_days", "Average dispatch days", "delivery", "Mean elapsed days from approval to carrier handoff.", "orders with both endpoints and non-negative duration", "Ineligible or negative durations are NULL.", "days", "order"),
        _metric("avg_transit_days", "Average transit days", "delivery", "Mean elapsed days from carrier handoff to customer delivery.", "delivered orders with both endpoints and non-negative duration", "Ineligible or negative durations are NULL.", "days", "order"),
        _metric("late_ratio", "Late-delivery ratio", "delivery", "Share delivered after the estimated delivery timestamp.", "delivered orders with actual and estimated timestamps", "Ineligible orders are NULL and excluded.", "ratio", "order"),
        _metric("avg_late_days", "Average late days", "delivery", "Mean positive elapsed days after the estimate among late orders.", "late delivered orders", "On-time and ineligible orders are excluded.", "days", "order"),
        _metric("avg_product_weight", "Average product weight", "product_logistics", "Mean valid item product weight converted from grams to kilograms.", "items with positive product weight", "Missing or non-positive weights are NULL.", "kg", "item"),
        _metric("avg_product_volume", "Average product volume", "product_logistics", "Mean length x height x width for valid item dimensions.", "items with all three positive dimensions", "Missing or non-positive dimensions are NULL.", "cm3", "item"),
        _metric("avg_freight_per_item", "Average freight per item", "freight", "Freight sum divided by items with non-null freight.", "items with freight", "Returns NULL when no item has freight.", "BRL/item", "item"),
        _metric("avg_freight_ratio", "Average freight ratio", "freight", "Mean item freight / (price + freight).", "items with non-null components and price + freight > 0", "The item ratio is NULL when the denominator is zero or negative.", "ratio", "item"),
    ]
}

METRICS = {
    category: [entry for entry in METRIC_INDEX.values() if entry["category"] == category]
    for category in ("volume", "value", "reviews", "delivery", "product_logistics", "freight")
}
