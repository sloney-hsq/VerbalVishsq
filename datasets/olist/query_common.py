"""Shared typed predicates and observation-field validation for Olist queries."""
from datetime import date, datetime
import math


OPS = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "between", "is_null", "is_not_null"}


def _valid(value, kind, entry=None):
    if value is None or isinstance(value, (dict, list, bool)):
        return False
    if kind == "quantitative":
        return isinstance(value, (int, float)) and math.isfinite(value)
    if kind == "temporal":
        if not isinstance(value, str):
            return False
        try:
            datetime.fromisoformat(value)
            return True
        except ValueError:
            try:
                date.fromisoformat(value)
                return True
            except ValueError:
                return False
    if kind in {"ordinal", "nominal"}:
        if entry and entry.get("value_type") == "number":
            return isinstance(value, (int, float)) and math.isfinite(value)
        return isinstance(value, str)
    return False


def normalize_filters(filters, field_index):
    if not isinstance(filters, list):
        raise ValueError("INVALID_FILTER_VALUE: filters must be an array")
    normalized = []
    for condition in filters:
        if not isinstance(condition, dict) or set(condition) - {"id", "field", "op", "value"}:
            raise ValueError("INVALID_FILTER_VALUE: invalid filter shape")
        field, op = condition.get("field"), condition.get("op")
        entry = field_index.get(field)
        if not entry or not entry.get("filterable", entry.get("groupable", False)) or op not in OPS or op not in entry.get("allowed_ops", OPS):
            raise ValueError("INVALID_FILTER_VALUE: unsupported field or operator")
        value = condition.get("value")
        if value is None and op in {"eq", "neq"} and "value" in condition:
            op = "is_null" if op == "eq" else "is_not_null"
        if op in {"is_null", "is_not_null"}:
            if "value" in condition and value is not None:
                raise ValueError("INVALID_FILTER_VALUE: null predicate cannot have value")
            result = {"field": field, "op": op}
        else:
            kind = entry["type"]
            if op == "in":
                if not isinstance(value, list) or not value or any(not _valid(v, kind, entry) for v in value):
                    raise ValueError("INVALID_FILTER_VALUE: in needs a nonempty same-type array")
                if len({type(v) for v in value}) != 1:
                    raise ValueError("INVALID_FILTER_VALUE: in values differ in type")
            elif op == "between":
                if not isinstance(value, list) or len(value) != 2 or any(not _valid(v, kind, entry) for v in value) or value[0] > value[1]:
                    raise ValueError("INVALID_FILTER_VALUE: between needs ascending endpoints")
            elif not _valid(value, kind, entry):
                raise ValueError("INVALID_FILTER_VALUE: invalid scalar")
            result = {"field": field, "op": op, "value": value}
        if "id" in condition:
            result["id"] = condition["id"]
        normalized.append(result)
    return normalized


def compile_filters(filters, field_index):
    clauses, params = [], []
    for item in normalize_filters(filters, field_index):
        column = '"' + field_index[item["field"]].get("column", item["field"]).replace('"', '""') + '"'
        op = item["op"]
        if op in {"is_null", "is_not_null"}:
            clauses.append(f"{column} IS {'NOT ' if op == 'is_not_null' else ''}NULL")
        elif op == "in":
            clauses.append(f"{column} IN ({', '.join('?' for _ in item['value'])})")
            params.extend(item["value"])
        elif op == "between":
            clauses.append(f"{column} BETWEEN ? AND ?")
            params.extend(item["value"])
        else:
            sign = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
            clauses.append(f"{column} {sign} ?")
            params.append(item["value"])
    return clauses, params


def validate_filter_conflicts(filters):
    """Reject explicit incompatible AND constraints before running a query."""
    by_field = {}
    for item in filters:
        by_field.setdefault(item["field"], []).append(item)
    for conditions in by_field.values():
        equals = [item["value"] for item in conditions if item["op"] == "eq"]
        if len(set(equals)) > 1:
            raise ValueError("FILTER_CONFLICT: incompatible equality conditions")
        if equals:
            value = equals[0]
            for item in conditions:
                op = item["op"]
                if (op == "neq" and value == item["value"] or op == "in" and value not in item["value"]
                    or op == "is_null" or op == "gt" and not value > item["value"]
                    or op == "gte" and not value >= item["value"] or op == "lt" and not value < item["value"]
                    or op == "lte" and not value <= item["value"] or op == "between" and not item["value"][0] <= value <= item["value"][1]):
                    raise ValueError("FILTER_CONFLICT: incompatible conditions")
        if any(item["op"] == "is_null" for item in conditions) and any(item["op"] in {"is_not_null", "gt", "gte", "lt", "lte", "in", "between"} for item in conditions):
            raise ValueError("FILTER_CONFLICT: null and non-null conditions")


def effective_filters(filters, field_index):
    if globals().get("PREDICATE") is not None and any(PREDICATE.is_or(item) for item in filters):
        normalized = PREDICATE.normalize(filters, field_index)
        default_applied = not any(not PREDICATE.is_or(item) and item["field"] == "order_status" for item in normalized)
        if default_applied:
            normalized = [{"field": "order_status", "op": "eq", "value": "delivered"}, *normalized]
        return normalized, default_applied
    normalized = normalize_filters(filters, field_index)
    validate_filter_conflicts(normalized)
    default_applied = not any(item["field"] == "order_status" for item in normalized)
    if default_applied:
        normalized = [{"field": "order_status", "op": "eq", "value": "delivered"}, *normalized]
    return normalized, default_applied


def validate_time_range(value, field_index):
    if value is None:
        return
    if not isinstance(value, dict) or set(value) - {"field", "start", "end"} or not ({"start", "end"} & value.keys()):
        raise ValueError("INVALID_FILTER_VALUE: invalid time_range")
    entry = field_index.get(value.get("field", "order_date"))
    if not entry or entry["type"] != "temporal":
        raise ValueError("INVALID_FILTER_VALUE: invalid time field")
    for key in ("start", "end"):
        if key in value and not _valid(value[key], "temporal"):
            raise ValueError("INVALID_FILTER_VALUE: invalid time boundary")
    if "start" in value and "end" in value and value["start"] >= value["end"]:
        raise ValueError("INVALID_FILTER_VALUE: start must precede end")


def observation_query(unit, fields, group_by, filters, time_range, field_index):
    """Select only registered observation columns; order rows survive item joins once."""
    if globals().get("PREDICATE") is not None:
        groups = [group_by] if group_by else []
        sql, params, _ = PREDICATE.observation_sql(unit, fields, groups, filters, time_range, field_index)
        return sql, params
    if unit not in {"order", "item"}:
        raise ValueError("INCOMPATIBLE_GRAIN: unknown observation unit")
    for field in fields:
        entry = field_index.get(field)
        if not entry or unit not in entry["observation_units"] or entry["type"] != "quantitative" or entry["groupable"]:
            raise ValueError("INCOMPATIBLE_GRAIN: invalid numeric observation field")
    if group_by:
        entry = field_index.get(group_by)
        if not entry or not entry["groupable"] or entry["type"] not in {"nominal", "ordinal", "temporal"}:
            raise ValueError("INCOMPATIBLE_GRAIN: invalid group field")
    normalized, _ = effective_filters(filters, field_index)
    validate_time_range(time_range, field_index)
    item_needed = unit == "order" and (group_by and field_index[group_by]["grain"] == "item" or any(field_index[item["field"]]["grain"] == "item" for item in normalized))
    alias = lambda field: ("i" if unit == "item" or field_index[field]["grain"] == "item" else "o")
    q = lambda field: f'{alias(field)}."{field_index[field].get("column", field)}"'
    select = [f"CASE WHEN {q(field)} BETWEEN 1 AND 5 THEN {q(field)} END AS \"{field}\"" if field == "review_score"
              else f"{q(field)} AS \"{field}\"" for field in fields]
    if group_by:
        select.append(f'{q(group_by)} AS "group"')
    if unit == "order":
        select.insert(0, 'o."order_id" AS observation_id')
        source = 'order_grain o JOIN item_grain i USING (order_id)' if item_needed else 'order_grain o'
    else:
        select.insert(0, "(i.\"order_id\" || ':' || CAST(i.\"order_item_id\" AS VARCHAR)) AS observation_id")
        source = 'item_grain i'
    clauses, params = [], []
    for condition in normalized:
        field, op = condition["field"], condition["op"]
        col = q(field)
        if op in {"is_null", "is_not_null"}:
            clauses.append(f"{col} IS {'NOT ' if op == 'is_not_null' else ''}NULL")
        elif op == "in":
            clauses.append(f"{col} IN ({', '.join('?' for _ in condition['value'])})")
            params.extend(condition["value"])
        elif op == "between":
            clauses.append(f"{col} BETWEEN ? AND ?")
            params.extend(condition["value"])
        else:
            sign = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
            clauses.append(f"{col} {sign} ?")
            params.append(condition["value"])
    if time_range:
        time_field = time_range.get("field", "order_date")
        for key, sign in (("start", ">="), ("end", "<")):
            if key in time_range:
                clauses.append(f"{q(time_field)} {sign} ?")
                params.append(time_range[key])
    distinct = "DISTINCT " if unit == "order" else ""
    return f"SELECT {distinct}{', '.join(select)} FROM {source} WHERE {' AND '.join(clauses)}", params
