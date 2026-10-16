"""Registered dynamic measure validation and exact evaluation."""
from collections import defaultdict
import math
import re

ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def quantile(values, q):
    values = sorted(values)
    if not values:
        return None
    pos = (len(values) - 1) * q
    lo = int(pos); hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def validate(measures, unit, fields, reserved=()):
    if not isinstance(measures, list) or len(measures) > 4:
        raise ValueError("INVALID_MEASURE: measures must contain at most four definitions")
    ids = [m.get("id") for m in measures if isinstance(m, dict)]
    if len(ids) != len(measures) or len(set(ids)) != len(ids):
        raise ValueError("INVALID_MEASURE: measure IDs must be unique")
    for measure in measures:
        mid, stat = measure.get("id"), measure.get("stat")
        if not isinstance(mid, str) or not ID.fullmatch(mid) or "__" in mid or mid in reserved:
            raise ValueError("INVALID_MEASURE: invalid or reserved id")
        if stat == "registered_ratio":
            if set(measure) != {"id", "stat", "formula_id"} or measure["formula_id"] != "freight_share_of_total" or unit != "item":
                raise ValueError("INVALID_MEASURE: invalid registered ratio")
            continue
        field = measure.get("field")
        if field not in fields or fields[field]["type"] != "quantitative" or unit not in fields[field]["observation_units"]:
            raise ValueError("INVALID_MEASURE: field is incompatible with unit")
        expected = {"id", "stat", "field"}
        if stat == "quantile":
            expected.add("q")
            if type(measure.get("q")) not in {int, float} or not 0 <= measure["q"] <= 1:
                raise ValueError("INVALID_MEASURE: invalid quantile")
        elif stat == "threshold_ratio":
            expected |= {"op", "value"}
            if (measure.get("op") not in {"eq", "neq", "gt", "gte", "lt", "lte"}
                    or type(measure.get("value")) not in {int, float} or not math.isfinite(measure["value"])):
                raise ValueError("INVALID_MEASURE: invalid threshold")
        elif stat not in {"mean", "median"}:
            raise ValueError("INVALID_MEASURE: unsupported statistic")
        if set(measure) != expected:
            raise ValueError("INVALID_MEASURE: invalid measure shape")


def resolve_quantile_filters(con, unit, filters, time_range, registry):
    return resolve_quantile_contexts(con, unit, [(filters, time_range)], registry, base_filters=filters)


def resolve_quantile_contexts(con, unit, contexts, registry, *, base_filters=None):
    predicate, fields = registry["predicate"], registry["fields"]
    normalized = predicate.normalize(base_filters if base_filters is not None else contexts[0][0], fields)
    rules = [item for item in normalized if not predicate.is_or(item) and item.get("op") == "quantile_between"]
    if not rules:
        return normalized, []
    base = [item for item in normalized if item not in rules]
    resolutions, materialized = [], list(base)
    for rule in rules:
        pooled = {}
        for filters, time_range in contexts:
            normalized_context = predicate.normalize(filters, fields)
            context_base = [item for item in normalized_context if item.get("op") != "quantile_between"]
            sql, params, _ = predicate.observation_sql(unit, [rule["field"]], [], context_base, time_range, fields)
            for row in con.execute(sql, params).fetchall():
                if row[1] is not None and math.isfinite(row[1]): pooled[row[0]] = row[1]
        values = list(pooled.values())
        if not values:
            raise ValueError("EMPTY_REFERENCE_POPULATION: quantile rule has no valid base observations")
        bounds = {}
        for side, op in (("lower", "gte"), ("upper", "lte")):
            if side in rule["value"]:
                actual = quantile(values, rule["value"][side])
                bounds[side] = actual
                materialized.append({"id": f"{rule.get('id', rule['field'])}_{side}",
                                     "field": rule["field"], "op": op, "value": actual})
        retained = [value for value in values if ("lower" not in bounds or value >= bounds["lower"])
                    and ("upper" not in bounds or value <= bounds["upper"])]
        resolutions.append({"id": rule.get("id"), "field": rule["field"],
            "probabilities": dict(rule["value"]), "bounds": bounds,
            "base_valid_count": len(values), "single_rule_excluded_count": len(values) - len(retained),
            "basis": "full_base_scope_without_quantile_rules"})
    return materialized, resolutions


def execute(con, arguments, scope, registry):
    unit, measures = arguments["unit"], arguments.get("measures", [])
    group_by = arguments.get("group_by", [])
    reserved = {"period_id", "period", "bucket_index", "bucket_start", "bucket_end", "bucket_present",
                "record_count", "segment", "segment_id", "breakdown", "share", "segment_denominator"}
    validate(measures, unit, registry["fields"], [*reserved, *group_by, *arguments.get("metrics", [])])
    value_fields = sorted({m.get("field") for m in measures if m.get("field")} |
                          ({"price", "freight_value"} if any(m["stat"] == "registered_ratio" for m in measures) else set()))
    if any(item.get("op") == "quantile_between" for item in (scope or []) if isinstance(item, dict)):
        raise ValueError("INVALID_FILTER_VALUE: quantile rules are local-only")
    resolved_filters, quantile_rules = resolve_quantile_filters(con, unit,
        [*(scope or []), *arguments.get("filters", [])], arguments.get("time_range"), registry)
    sql, params, effective = registry["predicate"].observation_sql(
        unit, value_fields, group_by, resolved_filters,
        arguments.get("time_range"), registry["fields"])
    raw = con.execute(sql, params).fetchall()
    groups = defaultdict(list)
    for row in raw:
        key = tuple(row[1 + len(value_fields):])
        groups[key].append(dict(zip(value_fields, row[1:1 + len(value_fields)])))
    if not group_by and not groups:
        groups[()] = []
    rows, row_valid_counts, row_eligible_counts = [], [], []
    eligible_counts = {}
    valid_counts, denominators = {m["id"]: {} for m in measures}, {}
    for key in sorted(groups, key=lambda x: str(x)):
        observations = groups[key]
        out = dict(zip(group_by, key))
        aligned_counts = {}
        label = "all" if not group_by else str(key[0] if len(key) == 1 else key)
        eligible_counts[label] = len(observations)
        for measure in measures:
            mid, stat = measure["id"], measure["stat"]
            if stat == "registered_ratio":
                pairs = [(o["price"], o["freight_value"]) for o in observations
                         if o.get("price") is not None and o.get("freight_value") is not None
                         and math.isfinite(o["price"]) and math.isfinite(o["freight_value"]) and o["price"] + o["freight_value"] > 0]
                denom = sum(p + f for p, f in pairs)
                value = sum(f for _, f in pairs) / denom if pairs and denom else None
                count = len(pairs)
            else:
                values = [o[measure["field"]] for o in observations if o.get(measure["field"]) is not None and math.isfinite(o[measure["field"]])]
                count = len(values)
                if stat == "mean": value = sum(values) / count if count else None
                elif stat == "median": value = quantile(values, .5)
                elif stat == "quantile": value = quantile(values, measure["q"])
                else:
                    op, threshold = measure["op"], measure["value"]
                    compare = {"eq": lambda a:a == threshold, "neq": lambda a:a != threshold,
                               "gt": lambda a:a > threshold, "gte": lambda a:a >= threshold,
                               "lt": lambda a:a < threshold, "lte": lambda a:a <= threshold}[op]
                    value = sum(compare(v) for v in values) / count if count else None
            out[mid] = value
            valid_counts[mid][label] = count
            aligned_counts[mid] = count
            denominators[mid] = "valid matched item pairs" if stat == "registered_ratio" else f"valid {measure.get('field')} observations"
        rows.append(out)
        row_valid_counts.append(aligned_counts)
        row_eligible_counts.append(len(observations))
    top_metadata = None
    top = arguments.get("top_k")
    if top is not None:
        if (not isinstance(top, dict) or set(top) != {"dimension", "metric", "k", "direction"}
                or top["dimension"] not in group_by or top["metric"] not in {m["id"] for m in measures}
                or type(top["k"]) is not int or not 1 <= top["k"] <= 50 or top["direction"] not in {"asc", "desc"}):
            raise ValueError("INVALID_MEASURE: invalid dynamic top_k")
        rank_args = {key: value for key, value in arguments.items() if key not in {"top_k", "having", "sort", "limit"}}
        rank_args["group_by"] = [top["dimension"]]
        rank_args["limit"] = 1_000_000
        rank_result = execute(con, rank_args, scope, registry)
        if rank_result["truncated"]:
            raise ValueError("RESULT_TOO_LARGE: dynamic Top K ranking exceeds one million groups")
        ranked = rank_result["rows"]
        ranked.sort(key=lambda row: (row[top["metric"]] is None, row[top["metric"]] if top["direction"] == "asc" else -(row[top["metric"]] or 0), str(row[top["dimension"]])))
        selected = [row[top["dimension"]] for row in ranked[:top["k"]]]
        rows = [row for row in rows if row.get(top["dimension"]) in selected]
        top_metadata = {**top, "selected_members": selected, "ranking_scope": "full_requested_time_range"}
    for condition in arguments.get("having", []):
        if not isinstance(condition, dict) or set(condition) != {"field", "op", "value"} or condition["field"] not in {m["id"] for m in measures}:
            raise ValueError("INVALID_MEASURE: invalid dynamic having")
        op, target = condition["op"], condition["value"]
        def keep(row):
            value = row.get(condition["field"])
            if value is None: return False
            if op == "between": return isinstance(target, list) and len(target) == 2 and target[0] <= value <= target[1]
            return {"eq": value == target, "neq": value != target, "gt": value > target, "gte": value >= target,
                    "lt": value < target, "lte": value <= target}.get(op, False)
        rows = [row for row in rows if keep(row)]
    sort = arguments.get("sort")
    if sort:
        if sort.get("field") not in {*group_by, *[m["id"] for m in measures]} or sort.get("direction") not in {"asc", "desc"}:
            raise ValueError("INVALID_MEASURE: invalid dynamic sort")
        field = sort["field"]
        rows.sort(key=lambda row: (row.get(field) is None, row.get(field)), reverse=sort["direction"] == "desc")
    limit = arguments.get("limit", 100)
    truncated = len(rows) > limit
    rows = rows[:limit]
    # Counts remain row-aligned after ranking/filtering.
    row_valid_counts = [{m["id"]: valid_counts[m["id"]]["all" if not group_by else str(row[group_by[0]] if len(group_by) == 1 else tuple(row[g] for g in group_by))]
                         for m in measures} for row in rows]
    row_eligible_counts = [eligible_counts["all" if not group_by else str(row[group_by[0]] if len(group_by) == 1 else tuple(row[g] for g in group_by))] for row in rows]
    columns = {field: {"type": registry["fields"][field]["type"], "source_field": field} for field in group_by}
    for measure in measures:
        unit_name = "ratio" if measure["stat"] in {"threshold_ratio", "registered_ratio"} else registry["fields"][measure["field"]]["unit"]
        columns[measure["id"]] = {"type": "quantitative", "unit": unit_name,
            "source_field": measure.get("field"), "stat": measure["stat"], "label": measure["id"]}
    return {"rows": rows, "columns": columns, "metadata": {"observation_unit": unit,
        "effective_filters": effective, "measure_definitions": {m["id"]: dict(m) for m in measures},
        "measure_valid_counts": valid_counts, "row_valid_counts": row_valid_counts,
        "row_eligible_counts": row_eligible_counts, "measure_denominators": denominators,
        "quantile_rules": quantile_rules, "quantile_combined_retained_count": len(raw) if quantile_rules else None,
        "top_k": top_metadata}, "truncated": truncated}
