"""Whitelisted, parameter-bound SQL construction for Olist exploration."""


ITEM_CATEGORIES = {"product", "seller"}


def _q(name):
    return '"' + name.replace('"', '""') + '"'


def _needs_item_source(fields, dimension_index):
    return any(dimension_index[field]["category"] in ITEM_CATEGORIES for field in fields)


def _filter_sql(filters, dimension_index):
    if globals().get("COMMON") is not None:
        return COMMON.compile_filters(filters, dimension_index)
    clauses = []
    params = []
    for condition in filters:
        if not isinstance(condition, dict) or set(condition) - {"field", "op", "value"}:
            raise ValueError("Each filter requires only field, op, and optional value")
        field = condition.get("field")
        if field not in dimension_index or not dimension_index[field]["groupable"]:
            raise ValueError("Unsupported Olist filter field")
        column = _q(dimension_index[field]["column"])
        op = condition.get("op")
        if op == "is_null":
            clauses.append(f"{column} IS NULL")
            continue
        if "value" not in condition:
            raise ValueError("Filter requires value")
        value = condition["value"]
        if op in {"eq", "neq"} and value is None:
            clauses.append(f"{column} IS {'NOT ' if op == 'neq' else ''}NULL")
        elif op in {"eq", "neq", "gte", "lte", "gt", "lt"}:
            if isinstance(value, (dict, list)) or isinstance(value, bool):
                raise ValueError("Filter requires a scalar value")
            operator = {"eq": "=", "neq": "<>", "gte": ">=", "lte": "<=", "gt": ">", "lt": "<"}[op]
            clauses.append(f"{column} {operator} ?")
            params.append(value)
        elif op == "in":
            if not isinstance(value, list) or not value or any(isinstance(item, (dict, list)) for item in value):
                raise ValueError("The in operator requires a non-empty scalar array")
            clauses.append(f"{column} IN ({', '.join('?' for _ in value)})")
            params.extend(value)
        elif op == "between":
            if (not isinstance(value, list) or len(value) != 2
                    or any(isinstance(item, (dict, list)) or item is None for item in value)):
                raise ValueError("The between operator requires exactly two non-null scalar values")
            clauses.append(f"{column} BETWEEN ? AND ?")
            params.extend(value)
        else:
            raise ValueError("Unsupported Olist filter operator")
    return clauses, params


def _time_sql(time_range, dimension_index):
    if time_range is None:
        return [], []
    if not isinstance(time_range, dict) or set(time_range) - {"field", "start", "end"}:
        raise ValueError("Invalid time_range")
    field = time_range.get("field", "order_date")
    entry = dimension_index.get(field)
    if entry is None or entry["category"] != "temporal" or not entry["groupable"]:
        raise ValueError("time_range field must be a registered temporal dimension")
    if "start" not in time_range and "end" not in time_range:
        raise ValueError("time_range requires start or end")
    column = _q(entry["column"])
    clauses, params = [], []
    if "start" in time_range:
        clauses.append(f"{column} >= ?")
        params.append(time_range["start"])
    if "end" in time_range:
        clauses.append(f"{column} < ?")
        params.append(time_range["end"])
    return clauses, params


def _scope(filters, *, explicit_status):
    return list(filters) if explicit_status else [{"field": "order_status", "op": "eq", "value": "delivered"}, *filters]


def _group_order_select(source, group_fields, dimension_index):
    dimensions = [
        f"{_q(dimension_index[field]['column'])} AS {_q(field)}"
        for field in group_fields
    ]
    dimension_groups = [_q(dimension_index[field]["column"]) for field in group_fields]
    common = [
        "ANY_VALUE(customer_unique_id) AS customer_unique_id",
        "ANY_VALUE(review_score) AS review_score",
        "ANY_VALUE(review_count) AS review_count",
        "ANY_VALUE(review_comment_present) AS review_comment_present",
        "ANY_VALUE(delivery_days) AS delivery_days",
        "ANY_VALUE(approval_days) AS approval_days",
        "ANY_VALUE(dispatch_days) AS dispatch_days",
        "ANY_VALUE(transit_days) AS transit_days",
        "ANY_VALUE(is_late) AS is_late",
        "ANY_VALUE(late_days) AS late_days",
    ]
    if source == "item_grain":
        item = [
            "COUNT(*)::BIGINT AS item_count",
            "COUNT(price)::BIGINT AS price_count",
            "SUM(price)::DOUBLE AS revenue",
            "COUNT(freight_value)::BIGINT AS freight_count",
            "SUM(freight_value)::DOUBLE AS freight_value",
            "SUM(total_item_value)::DOUBLE AS total_order_value",
            "SUM(product_weight_kg)::DOUBLE AS product_weight_sum",
            "COUNT(product_weight_kg)::BIGINT AS product_weight_count",
            "SUM(product_volume_cm3)::DOUBLE AS product_volume_sum",
            "COUNT(product_volume_cm3)::BIGINT AS product_volume_count",
            "SUM(freight_ratio)::DOUBLE AS freight_ratio_sum",
            "COUNT(freight_ratio)::BIGINT AS freight_ratio_count",
        ]
    else:
        item = [
            "ANY_VALUE(item_count)::BIGINT AS item_count",
            "ANY_VALUE(price_count)::BIGINT AS price_count",
            "ANY_VALUE(revenue)::DOUBLE AS revenue",
            "ANY_VALUE(freight_count)::BIGINT AS freight_count",
            "ANY_VALUE(freight_value)::DOUBLE AS freight_value",
            "ANY_VALUE(total_order_value)::DOUBLE AS total_order_value",
            "ANY_VALUE(product_weight_sum)::DOUBLE AS product_weight_sum",
            "ANY_VALUE(product_weight_count)::BIGINT AS product_weight_count",
            "ANY_VALUE(product_volume_sum)::DOUBLE AS product_volume_sum",
            "ANY_VALUE(product_volume_count)::BIGINT AS product_volume_count",
            "ANY_VALUE(freight_ratio_sum)::DOUBLE AS freight_ratio_sum",
            "ANY_VALUE(freight_ratio_count)::BIGINT AS freight_ratio_count",
        ]
    select = [*dimensions, "order_id", *common, *item]
    group = [*dimension_groups, "order_id"]
    return ",\n                ".join(select), ", ".join(group)


METRIC_SQL = {
    "order_count": "COUNT(*)::BIGINT",
    "reviewed_order_count": "COUNT(CASE WHEN review_score BETWEEN 1 AND 5 THEN 1 END)::BIGINT",
    "valid_delivery_order_count": "COUNT(delivery_days)::BIGINT",
    "late_eligible_order_count": "COUNT(is_late)::BIGINT",
    "item_count": "COALESCE(SUM(item_count), 0)::BIGINT",
    "unique_customer_count": "COUNT(DISTINCT customer_unique_id)::BIGINT",
    "revenue": "COALESCE(SUM(revenue), 0)::DOUBLE",
    "freight_value": "COALESCE(SUM(freight_value), 0)::DOUBLE",
    "total_order_value": "COALESCE(SUM(total_order_value), 0)::DOUBLE",
    "avg_order_value": "(SUM(revenue) / NULLIF(COUNT(*), 0))::DOUBLE",
    "avg_item_price": "(SUM(revenue) / NULLIF(SUM(price_count), 0))::DOUBLE",
    "avg_review_score": "AVG(review_score)::DOUBLE",
    "review_comment_ratio": "(SUM(review_comment_present) / NULLIF(COUNT_IF(review_count > 0), 0))::DOUBLE",
    "low_score_ratio": "(COUNT_IF(review_score <= 2) / NULLIF(COUNT(review_score), 0))::DOUBLE",
    "one_star_ratio": "(COUNT_IF(review_score = 1) / NULLIF(COUNT(review_score), 0))::DOUBLE",
    "five_star_ratio": "(COUNT_IF(review_score = 5) / NULLIF(COUNT(review_score), 0))::DOUBLE",
    "avg_delivery_days": "AVG(delivery_days)::DOUBLE",
    "avg_approval_days": "AVG(approval_days)::DOUBLE",
    "avg_dispatch_days": "AVG(dispatch_days)::DOUBLE",
    "avg_transit_days": "AVG(transit_days)::DOUBLE",
    "late_ratio": "(SUM(is_late) / NULLIF(COUNT(is_late), 0))::DOUBLE",
    "avg_late_days": "AVG(CASE WHEN is_late = 1 THEN late_days END)::DOUBLE",
    "avg_product_weight": "(SUM(product_weight_sum) / NULLIF(SUM(product_weight_count), 0))::DOUBLE",
    "avg_product_volume": "(SUM(product_volume_sum) / NULLIF(SUM(product_volume_count), 0))::DOUBLE",
    "avg_freight_per_item": "(SUM(freight_value) / NULLIF(SUM(freight_count), 0))::DOUBLE",
    "avg_freight_ratio": "(SUM(freight_ratio_sum) / NULLIF(SUM(freight_ratio_count), 0))::DOUBLE",
}


def _final_sql(group_fields, metrics, *, segment=False):
    selected = [_q(field) for field in group_fields]
    selected.extend(f"{METRIC_SQL[metric]} AS {_q(metric)}" for metric in metrics)
    group = f"GROUP BY {', '.join(_q(field) for field in group_fields)}" if group_fields else ""
    return ",\n            ".join(selected), group


def build_aggregate(arguments, scope, dimension_index, metric_index):
    group_by = arguments["group_by"]
    metrics = arguments["metrics"]
    if any(field not in dimension_index or not dimension_index[field]["groupable"] for field in group_by):
        raise ValueError("Unsupported Olist group_by field")
    if any(metric not in metric_index for metric in metrics):
        raise ValueError("Unsupported Olist metric")
    filters = [*(scope or []), *arguments.get("filters", [])]
    explicit_status = any(item.get("field") == "order_status" for item in filters if isinstance(item, dict))
    filters = _scope(filters, explicit_status=explicit_status)
    filter_fields = [item.get("field") for item in filters if isinstance(item, dict) and item.get("field") in dimension_index]
    source = "item_grain" if _needs_item_source([*group_by, *filter_fields], dimension_index) else "order_grain"
    clauses, params = _filter_sql(filters, dimension_index)
    time_clauses, time_params = _time_sql(arguments.get("time_range"), dimension_index)
    clauses.extend(time_clauses)
    params.extend(time_params)
    select_group_order, group_order_by = _group_order_select(source, group_by, dimension_index)
    having = arguments.get("having", [])
    if not isinstance(having, list):
        raise ValueError("INVALID_FILTER_VALUE: having must be a list")
    additional = []
    having_clauses, having_params = [], []
    for condition in having:
        if not isinstance(condition, dict) or set(condition) != {"field", "op", "value"} or condition["field"] not in metric_index:
            raise ValueError("INVALID_FILTER_VALUE: invalid having metric")
        field, op, value = condition["field"], condition["op"], condition["value"]
        if field not in metrics and field not in additional:
            additional.append(field)
        if op == "between":
            if not isinstance(value, list) or len(value) != 2 or any(type(v) not in (int, float) for v in value) or value[0] > value[1]:
                raise ValueError("INVALID_FILTER_VALUE: invalid having range")
            having_clauses.append(f"{_q(field)} BETWEEN ? AND ?")
            having_params.extend(value)
        elif op in {"eq", "neq", "gt", "gte", "lt", "lte"} and type(value) in (int, float):
            sign = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
            having_clauses.append(f"{_q(field)} {sign} ?")
            having_params.append(value)
        else:
            raise ValueError("INVALID_FILTER_VALUE: invalid having condition")
    final_select, final_group = _final_sql(group_by, [*metrics, *additional])
    top_k = arguments.get("top_k")
    rank_sql = "chosen AS (SELECT * FROM group_order)"
    if top_k is not None:
        if (not isinstance(top_k, dict) or set(top_k) != {"dimension", "metric", "k", "direction"}
                or top_k["dimension"] not in group_by or top_k["metric"] not in metric_index
                or type(top_k["k"]) is not int or not 1 <= top_k["k"] <= 50
                or top_k["direction"] not in {"asc", "desc"}):
            raise ValueError("INVALID_FILTER_VALUE: invalid top_k")
        dim = _q(top_k["dimension"])
        rank_sql = (f"ranked AS (SELECT {dim}, {METRIC_SQL[top_k['metric']]} AS rank_value FROM group_order "
                    f"GROUP BY {dim} ORDER BY rank_value {top_k['direction'].upper()} NULLS LAST, {dim} ASC LIMIT {top_k['k']}), "
                    f"chosen AS (SELECT group_order.* FROM group_order JOIN ranked USING ({dim}))")
    sort = arguments.get("sort")
    if sort is not None:
        if sort["field"] not in {*group_by, *metrics}:
            raise ValueError("Sort field must be a requested group or metric")
        order = f"ORDER BY {_q(sort['field'])} {sort['direction'].upper()} NULLS LAST"
    elif group_by:
        order = "ORDER BY " + ", ".join(f"{_q(field)} ASC NULLS LAST" for field in group_by)
    else:
        order = ""
    limit = arguments.get("limit", 100)
    visible = ", ".join(_q(field) for field in [*group_by, *metrics])
    sql = f"""
        WITH group_order AS (
            SELECT {select_group_order}
            FROM {source}
            WHERE {' AND '.join(clauses) if clauses else 'TRUE'}
            GROUP BY {group_order_by}
        ), {rank_sql}, aggregated AS (
            SELECT {final_select} FROM chosen {final_group}
        )
        SELECT {visible} FROM aggregated
        {'WHERE ' + ' AND '.join(having_clauses) if having_clauses else ''}
        {order}
        LIMIT ?
    """
    return sql, [*params, *having_params, limit + 1], [*group_by, *metrics], limit


def build_segments(arguments, scope, dimension_index, metric_index):
    segments = arguments["segments"]
    metrics = arguments["metrics"]
    if any(metric not in metric_index for metric in metrics):
        raise ValueError("Unsupported Olist metric")
    parsed = []
    all_segment_fields = []
    for index, segment in enumerate(segments):
        dimensions = {key: value for key, value in segment.items() if key not in {"name", "label"}}
        if not dimensions:
            raise ValueError("Each segment requires at least one dimension")
        if any(field not in dimension_index or not dimension_index[field]["groupable"] for field in dimensions):
            raise ValueError("Unsupported Olist segment dimension")
        if any(isinstance(value, (dict, list)) for value in dimensions.values()):
            raise ValueError("Segment dimension values must be scalar")
        label = segment.get("label") or segment.get("name") or ", ".join(f"{key}={value}" for key, value in dimensions.items())
        parsed.append((index, label, dimensions))
        all_segment_fields.extend(dimensions)
    common_filters = [*(scope or []), *arguments.get("filters", [])]
    explicit_status = any(item.get("field") == "order_status" for item in common_filters if isinstance(item, dict)) or "order_status" in all_segment_fields
    common_filters = _scope(common_filters, explicit_status=explicit_status)
    filter_fields = [item.get("field") for item in common_filters if isinstance(item, dict) and item.get("field") in dimension_index]
    source = "item_grain" if _needs_item_source([*all_segment_fields, *filter_fields], dimension_index) else "order_grain"
    common_clauses, common_params = _filter_sql(common_filters, dimension_index)
    time_clauses, time_params = _time_sql(arguments.get("time_range"), dimension_index)
    common_clauses.extend(time_clauses)
    unions, params, seed_params = [], [], []
    for index, label, dimensions in parsed:
        seed_params.extend([index, label])
        segment_filters = [{"field": field, "op": "eq", "value": value} for field, value in dimensions.items()]
        segment_clauses, segment_params = _filter_sql(segment_filters, dimension_index)
        unions.append(
            f"SELECT ?::INTEGER AS _segment_index, ?::VARCHAR AS segment, * FROM {source} "
            f"WHERE {' AND '.join([*common_clauses, *segment_clauses]) if common_clauses or segment_clauses else 'TRUE'}"
        )
        params.extend([index, label, *common_params, *time_params, *segment_params])
    select_group_order, group_order_by = _group_order_select("item_grain" if source == "item_grain" else "order_grain", ["_segment_index", "segment"], {
        **dimension_index,
        "_segment_index": {"column": "_segment_index"},
        "segment": {"column": "segment"},
    })
    final_select, final_group = _final_sql(["_segment_index", "segment"], metrics)
    limit = arguments.get("limit", 100)
    zero_metrics = {"order_count", "item_count", "unique_customer_count", "revenue", "freight_value", "total_order_value"}
    result_metrics = ", ".join(
        f"COALESCE(a.{_q(metric)}, 0) AS {_q(metric)}" if metric in zero_metrics
        else f"a.{_q(metric)} AS {_q(metric)}"
        for metric in metrics
    )
    seeds = ", ".join("(?::INTEGER, ?::VARCHAR)" for _ in parsed)
    sql = f"""
        WITH segment_seed(_segment_index, segment) AS (VALUES {seeds}),
        segmented AS ({' UNION ALL '.join(unions)}),
        group_order AS (
            SELECT {select_group_order}
            FROM segmented
            GROUP BY {group_order_by}
        ), aggregated AS (
            SELECT {final_select}
            FROM group_order
            {final_group}
        )
        SELECT s.segment, {result_metrics}
        FROM segment_seed s
        LEFT JOIN aggregated a USING (_segment_index, segment)
        ORDER BY s._segment_index
        LIMIT ?
    """
    return sql, [*seed_params, *params, limit + 1], ["segment", *metrics], limit
