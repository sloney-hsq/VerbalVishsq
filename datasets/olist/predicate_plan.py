"""Bounded predicate planning shared by Olist analytical tools."""
from datetime import date, datetime
import math

OPS = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "between", "is_null", "is_not_null"}


def _q(name):
    return '"' + name.replace('"', '""') + '"'


def is_or(item):
    return isinstance(item, dict) and item.get("op") == "or"


def flatten(filters):
    for item in filters:
        if is_or(item):
            for branch in item["branches"]:
                yield from branch["all"]
        else:
            yield item


def normalize(filters, fields, *, allow_quantile=True, allow_or=True):
    if not isinstance(filters, list) or len(filters) > 20:
        raise ValueError("INVALID_FILTER_VALUE: filters must be an array of at most 20 clauses")
    result, leaf_count = [], 0
    for item in filters:
        if is_or(item):
            if not allow_or:
                raise ValueError("INVALID_FILTER_VALUE: nested OR is not allowed")
            if set(item) - {"id", "op", "branches"} or set(item) < {"op", "branches"} or ("id" in item and not isinstance(item["id"], str)):
                raise ValueError("INVALID_FILTER_VALUE: invalid OR group")
            branches = item["branches"]
            if not isinstance(branches, list) or not 2 <= len(branches) <= 8:
                raise ValueError("INVALID_FILTER_VALUE: OR needs 2 to 8 branches")
            normalized = []
            for branch in branches:
                if not isinstance(branch, dict) or set(branch) != {"all"} or not isinstance(branch["all"], list) or not 1 <= len(branch["all"]) <= 8:
                    raise ValueError("INVALID_FILTER_VALUE: invalid OR branch")
                leaves = normalize(branch["all"], fields, allow_quantile=False, allow_or=False)
                if any(leaf["field"] == "order_status" for leaf in leaves):
                    raise ValueError("INVALID_FILTER_VALUE: order_status is not allowed inside OR")
                normalized.append({"all": leaves})
                leaf_count += len(leaves)
            result.append({**({"id": item["id"]} if "id" in item else {}), "op": "or", "branches": normalized})
            continue
        if not isinstance(item, dict) or set(item) - {"id", "field", "op", "value"}:
            raise ValueError("INVALID_FILTER_VALUE: invalid filter shape")
        field, op = item.get("field"), item.get("op")
        entry = fields.get(field)
        if not entry or not entry.get("filterable", entry.get("groupable", False)):
            raise ValueError("INVALID_FILTER_VALUE: unsupported field")
        if op == "quantile_between":
            if not allow_quantile or entry["type"] != "quantitative":
                raise ValueError("INVALID_FILTER_VALUE: quantile rule is not allowed here")
            value = item.get("value")
            if not isinstance(value, dict) or set(value) - {"lower", "upper"} or not value:
                raise ValueError("INVALID_FILTER_VALUE: invalid quantile range")
            lo, hi = value.get("lower"), value.get("upper")
            if any(type(v) not in {int, float} or not 0 <= v <= 1 for v in value.values()) or lo is not None and hi is not None and lo >= hi:
                raise ValueError("INVALID_FILTER_VALUE: invalid quantile probabilities")
        elif op not in OPS or op not in entry.get("allowed_ops", OPS):
            raise ValueError("INVALID_FILTER_VALUE: unsupported operator")
        else:
            has_value = "value" in item
            value = item.get("value")
            if op in {"is_null", "is_not_null"}:
                if has_value and value is not None:
                    raise ValueError("INVALID_FILTER_VALUE: null predicate cannot have value")
            else:
                if not has_value:
                    raise ValueError("INVALID_FILTER_VALUE: predicate requires value")
                values = value if op in {"in", "between"} else [value]
                if op == "in" and (not isinstance(value, list) or not value):
                    raise ValueError("INVALID_FILTER_VALUE: in requires nonempty values")
                if op == "between" and (not isinstance(value, list) or len(value) != 2):
                    raise ValueError("INVALID_FILTER_VALUE: between requires two endpoints")
                if not isinstance(values, list): values = [values]
                for candidate in values:
                    if isinstance(candidate, (bool, dict, list)) or candidate is None:
                        raise ValueError("INVALID_FILTER_VALUE: invalid filter value")
                    if entry["type"] == "quantitative" or entry.get("value_type") == "number":
                        if type(candidate) not in {int, float} or not math.isfinite(candidate):
                            raise ValueError("INVALID_FILTER_VALUE: numeric filter needs finite number")
                    elif entry["type"] == "temporal":
                        if not isinstance(candidate, str): raise ValueError("INVALID_FILTER_VALUE: temporal filter needs ISO string")
                        try: datetime.fromisoformat(candidate)
                        except ValueError:
                            try: date.fromisoformat(candidate)
                            except ValueError as exc: raise ValueError("INVALID_FILTER_VALUE: invalid temporal value") from exc
                    elif not isinstance(candidate, str):
                        raise ValueError("INVALID_FILTER_VALUE: categorical filter needs string")
                if op == "between":
                    try:
                        if value[0] > value[1]: raise ValueError("INVALID_FILTER_VALUE: between requires ascending endpoints")
                    except TypeError as exc:
                        raise ValueError("INVALID_FILTER_VALUE: between endpoints must share a comparable type") from exc
        result.append(dict(item))
        leaf_count += 1
    if leaf_count > 64:
        raise ValueError("INVALID_FILTER_VALUE: filters exceed 64 leaves")
    return result


def _leaf_sql(item, fields, params):
    entry = fields[item["field"]]
    alias = "i" if entry["grain"] == "item" else "o"
    col = f"{alias}.{_q(entry.get('column', item['field']))}"
    op = item["op"]
    if op in {"is_null", "is_not_null"}:
        return f"{col} IS {'NOT ' if op == 'is_not_null' else ''}NULL"
    value = item.get("value")
    if op == "in":
        params.extend(value)
        return f"{col} IN ({', '.join('?' for _ in value)})"
    if op == "between":
        params.extend(value)
        return f"{col} BETWEEN ? AND ?"
    params.append(value)
    sign = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
    return f"{col} {sign} ?"


def compile_where(filters, fields):
    filters = normalize(filters, fields)
    if not any(not is_or(x) and x["field"] == "order_status" for x in filters):
        filters = [{"field": "order_status", "op": "eq", "value": "delivered"}, *filters]
    params, clauses = [], []
    for item in filters:
        if is_or(item):
            parts = []
            for branch in item["branches"]:
                parts.append("(" + " AND ".join(_leaf_sql(x, fields, params) for x in branch["all"]) + ")")
            clauses.append("(" + " OR ".join(parts) + ")")
        else:
            clauses.append(_leaf_sql(item, fields, params))
    return " AND ".join(clauses) if clauses else "TRUE", params, filters


def observation_sql(unit, value_fields, group_by, filters, time_range, fields):
    if unit not in {"order", "item"}:
        raise ValueError("INCOMPATIBLE_GRAIN: unit must be order or item")
    for field in value_fields:
        if field not in fields or unit not in fields[field]["observation_units"]:
            raise ValueError("INCOMPATIBLE_GRAIN: field is unavailable at requested unit")
    for field in group_by:
        if field not in fields or not fields[field].get("groupable"):
            raise ValueError("INCOMPATIBLE_GRAIN: invalid group field")
    where, params, effective = compile_where(filters, fields)
    if time_range:
        field = time_range.get("field", "order_date")
        col = f'o.{_q(fields[field].get("column", field))}'
        if "start" in time_range:
            where += f" AND {col} >= ?"; params.append(time_range["start"])
        if "end" in time_range:
            where += f" AND {col} < ?"; params.append(time_range["end"])
    def qfield(f):
        raw = f'{"i" if fields[f]["grain"] == "item" else "o"}.{_q(fields[f].get("column", f))}'
        return f"CASE WHEN {raw} BETWEEN 1 AND 5 THEN {raw} END" if f == "review_score" else raw
    observation = 'o."order_id"' if unit == "order" else '(i."order_id" || \':\' || CAST(i."order_item_id" AS VARCHAR))'
    selected = [f"{observation} AS observation_id"]
    selected += [f'{qfield(f)} AS {_q(f)}' for f in value_fields]
    selected += [f'{qfield(f)} AS {_q(f)}' for f in group_by]
    distinct = "DISTINCT " if unit == "order" else ""
    item_guard = ' AND i."order_id" IS NOT NULL' if unit == "item" else ""
    sql = f"SELECT {distinct}{', '.join(selected)} FROM order_grain o LEFT JOIN item_grain i USING(order_id) WHERE ({where}){item_guard}"
    return sql, params, effective
