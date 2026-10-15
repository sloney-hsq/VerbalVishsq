"""Shared typed predicates and observation-field validation for Olist queries."""
from datetime import date, datetime
import math


OPS = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "between", "is_null", "is_not_null"}


def _valid(value, kind):
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
    if kind == "ordinal":
        return isinstance(value, (int, float, str)) and (not isinstance(value, float) or math.isfinite(value))
    return isinstance(value, (str, int, float)) and (not isinstance(value, float) or math.isfinite(value))


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
        if value is None and op in {"eq", "neq"}:
            op = "is_null" if op == "eq" else "is_not_null"
        if op in {"is_null", "is_not_null"}:
            if "value" in condition and value is not None:
                raise ValueError("INVALID_FILTER_VALUE: null predicate cannot have value")
            result = {"field": field, "op": op}
        else:
            kind = entry["type"]
            if op == "in":
                if not isinstance(value, list) or not value or any(not _valid(v, kind) for v in value):
                    raise ValueError("INVALID_FILTER_VALUE: in needs a nonempty same-type array")
                if len({type(v) for v in value}) != 1:
                    raise ValueError("INVALID_FILTER_VALUE: in values differ in type")
            elif op == "between":
                if not isinstance(value, list) or len(value) != 2 or any(not _valid(v, kind) for v in value) or value[0] > value[1]:
                    raise ValueError("INVALID_FILTER_VALUE: between needs ascending endpoints")
            elif not _valid(value, kind):
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
