"""Dataset-neutral validation for registered typed filter fields."""
from datetime import datetime
from math import isfinite

OPS = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "between", "is_null", "is_not_null"}


def _valid(value, entry):
    if value is None or isinstance(value, (dict, list, bool)):
        return False
    kind = entry.get("type")
    if kind == "quantitative" or entry.get("value_type") == "number":
        return type(value) in {int, float} and isfinite(value)
    if kind == "temporal":
        if not isinstance(value, str):
            return False
        try:
            datetime.fromisoformat(value)
            return True
        except ValueError:
            return False
    return isinstance(value, str) if kind in {"ordinal", "nominal"} else False


def normalize_filters(filters, field_index, _nested=False):
    if not isinstance(filters, list):
        raise ValueError("INVALID_FILTER_VALUE: filters must be an array")
    if not _nested and len(filters) > 20:
        raise ValueError("INVALID_FILTER_VALUE: filters exceed 20 top-level clauses")
    normalized = []
    for item in filters:
        if isinstance(item, dict) and item.get("op") == "or":
            if _nested:
                raise ValueError("INVALID_FILTER_VALUE: nested OR is not allowed")
            if set(item) != {"id", "op", "branches"} or not isinstance(item["id"], str):
                raise ValueError("INVALID_FILTER_VALUE: invalid OR group")
            branches = item["branches"]
            if not isinstance(branches, list) or not 2 <= len(branches) <= 8:
                raise ValueError("INVALID_FILTER_VALUE: invalid OR branches")
            normalized_branches = []
            for branch in branches:
                if not isinstance(branch, dict) or set(branch) != {"all"} or not isinstance(branch["all"], list) or not 1 <= len(branch["all"]) <= 8:
                    raise ValueError("INVALID_FILTER_VALUE: invalid OR branch")
                leaves = normalize_filters(branch["all"], field_index, True)
                if any(leaf.get("field") == "order_status" for leaf in leaves):
                    raise ValueError("INVALID_FILTER_VALUE: order_status is not allowed inside OR")
                normalized_branches.append({"all": leaves})
            normalized.append({"id": item["id"], "op": "or", "branches": normalized_branches})
            continue
        if not isinstance(item, dict) or set(item) - {"id", "field", "op", "value"}:
            raise ValueError("INVALID_FILTER_VALUE: invalid filter shape")
        field, op = item.get("field"), item.get("op")
        entry = field_index.get(field)
        if not entry or not entry.get("filterable", entry.get("groupable", False)) or op not in entry.get("allowed_ops", OPS):
            raise ValueError("INVALID_FILTER_VALUE: unsupported field or operator")
        if op in {"eq", "neq"} and "value" in item and item["value"] is None:
            op = "is_null" if op == "eq" else "is_not_null"
        if op in {"is_null", "is_not_null"}:
            if item.get("value") is not None:
                raise ValueError("INVALID_FILTER_VALUE: null predicate cannot have value")
            result = {"field": field, "op": op}
        else:
            if "value" not in item:
                raise ValueError("INVALID_FILTER_VALUE: predicate requires value")
            value = item["value"]
            if op == "in":
                if not isinstance(value, list) or not value or any(not _valid(v, entry) for v in value) or len({type(v) for v in value}) != 1:
                    raise ValueError("INVALID_FILTER_VALUE: in needs same-type values")
            elif op == "between":
                if not isinstance(value, list) or len(value) != 2 or any(not _valid(v, entry) for v in value) or value[0] > value[1]:
                    raise ValueError("INVALID_FILTER_VALUE: between needs ascending endpoints")
            elif not _valid(value, entry):
                raise ValueError("INVALID_FILTER_VALUE: invalid scalar")
            result = {"field": field, "op": op, "value": value}
        if "id" in item:
            result["id"] = item["id"]
        normalized.append(result)
    if not _nested:
        leaf_count = sum(sum(len(branch["all"]) for branch in item["branches"]) if item.get("op") == "or" else 1
                         for item in normalized)
        if leaf_count > 64:
            raise ValueError("INVALID_FILTER_VALUE: filters exceed 64 leaves")
    return normalized


def validate_filter_conflicts(filters):
    by_field = {}
    for item in filters:
        if item.get("op") == "or":
            for branch in item["branches"]:
                validate_filter_conflicts(branch["all"])
            continue
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
