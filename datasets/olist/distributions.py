"""Complete-data numeric distributions for the registered Olist grains."""
from bisect import bisect_right
from collections import defaultdict
import math


def _quantile(sorted_values, fraction):
    position = (len(sorted_values) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def summarize_box(values):
    values = sorted(values)
    if not values:
        return {"q1": None, "median": None, "q3": None, "whisker_low": None,
                "whisker_high": None, "outlier_count": 0}
    q1, median, q3 = (_quantile(values, p) for p in (0.25, 0.5, 0.75))
    span = q3 - q1
    inside = [value for value in values if q1 - 1.5 * span <= value <= q3 + 1.5 * span]
    return {"q1": q1, "median": median, "q3": q3, "whisker_low": inside[0],
            "whisker_high": inside[-1], "outlier_count": len(values) - len(inside)}


def bin_edges(values, bins):
    if not isinstance(bins, dict) or len(bins) != 1:
        raise ValueError("INVALID_FILTER_VALUE: bins needs one mode")
    if "edges" in bins:
        edges = bins["edges"]
        if not isinstance(edges, list) or not 2 <= len(edges) <= 101 or any(type(v) not in (int, float) or not math.isfinite(v) for v in edges) or any(a >= b for a, b in zip(edges, edges[1:])):
            raise ValueError("INVALID_FILTER_VALUE: invalid bin edges")
        return edges if values else []
    if "count" in bins:
        count = bins["count"]
        if type(count) is not int or not 1 <= count <= 100:
            raise ValueError("INVALID_FILTER_VALUE: invalid bin count")
        if not values:
            return []
        lo, hi = min(values), max(values)
        if lo == hi:
            width = max(abs(lo) * 0.1, 1.0)
            return [lo - width / 2, lo + width / 2]
        return [lo + (hi - lo) * index / count for index in range(count)] + [hi]
    if "step" in bins:
        step = bins["step"]
        if type(step) not in (int, float) or not math.isfinite(step) or step <= 0:
            raise ValueError("INVALID_FILTER_VALUE: invalid bin step")
        if not values:
            return []
        lo, hi = min(values), max(values)
        if lo == hi:
            width = max(abs(lo) * 0.1, 1.0)
            return [lo - width / 2, lo + width / 2]
        count = math.ceil((hi - lo) / step)
        if count > 100:
            raise ValueError("RESULT_TOO_LARGE: too many bins")
        return [lo + index * step for index in range(count)] + [max(hi, lo + count * step)]
    raise ValueError("INVALID_FILTER_VALUE: invalid bins")


def execute_distribution(con, arguments, scope, registry):
    unit, field = arguments["unit"], arguments["field"]
    group_by = arguments.get("group_by")
    if isinstance(group_by, list):
        if len(group_by) > 1:
            raise ValueError("INCOMPATIBLE_GRAIN: distribution supports one group")
        group_by = group_by[0] if group_by else None
    output = arguments.get("output", "histogram")
    if output not in {"histogram", "box_summary"} or (output == "box_summary" and "bins" in arguments):
        raise ValueError("INVALID_FILTER_VALUE: invalid distribution output")
    common = registry["common"]
    requested_filters = [*(scope or []), *arguments.get("filters", [])]
    effective, default_applied = common.effective_filters(requested_filters, registry["fields"])
    sql, params = common.observation_query(unit, [field], group_by, requested_filters, arguments.get("time_range"), registry["fields"])
    result = con.execute(sql, params).fetchall()
    groups = defaultdict(list)
    for _, value, *tail in result:
        groups[tail[0] if group_by else None].append(value)
    if len(groups) > 30:
        raise ValueError("RESULT_TOO_LARGE: distribution has over 30 groups")
    valid = {group: [value for value in values if value is not None and math.isfinite(value)] for group, values in groups.items()}
    all_values = [value for values in valid.values() for value in values]
    metadata = {"observation_unit": unit, "field": field, "group_by": group_by,
                "eligible_count": len(result), "valid_count": len(all_values),
                "missing_count": len(result) - len(all_values), "effective_filters": effective,
                "default_scope_applied": default_applied, "time_range": arguments.get("time_range"),
                "overlaps_across_groups": bool(unit == "order" and group_by and registry["fields"][group_by]["grain"] == "item")}
    rows = []
    if output == "box_summary":
        for group in sorted(groups, key=lambda value: str(value)):
            values = valid[group]
            row = {**summarize_box(values), "valid_count": len(values), "missing_count": len(groups[group]) - len(values)}
            if group_by:
                row["group"] = group
            rows.append(row)
        columns = {name: {"type": "quantitative", "source_field": field, "unit": registry["fields"][field]["unit"]} for name in ("q1", "median", "q3", "whisker_low", "whisker_high")}
        columns.update({name: {"type": "quantitative", "unit": "observations"} for name in ("valid_count", "missing_count", "outlier_count")})
        kind = "box_summary"
    else:
        edges = bin_edges(all_values, arguments.get("bins", {"count": 20}))
        metadata["bin_edges"] = edges
        metadata["group_counts"] = {}
        for group in sorted(groups, key=lambda value: str(value)):
            values = valid[group]
            counts = [0] * (len(edges) - 1)
            under = over = 0
            for value in values:
                if value < edges[0]:
                    under += 1
                elif value > edges[-1]:
                    over += 1
                else:
                    index = min(bisect_right(edges, value) - 1, len(counts) - 1)
                    counts[index] += 1
            metadata["group_counts"][str(group)] = {"valid_count": len(values), "missing_count": len(groups[group]) - len(values),
                                                    "underflow_count": under, "overflow_count": over}
            for index, count in enumerate(counts):
                row = {"bin_start": edges[index], "bin_end": edges[index + 1], "count": count,
                       "proportion": count / len(values) if values else None}
                if group_by:
                    row["group"] = group
                rows.append(row)
        columns = {"bin_start": {"type": "quantitative", "source_field": field, "unit": registry["fields"][field]["unit"]},
                   "bin_end": {"type": "quantitative", "source_field": field, "unit": registry["fields"][field]["unit"]},
                   "count": {"type": "quantitative", "unit": "observations"}, "proportion": {"type": "quantitative", "unit": "ratio"}}
        kind = "histogram"
    if group_by:
        columns["group"] = {"type": registry["fields"][group_by]["type"], "source_field": group_by}
    if len(rows) > 5000:
        raise ValueError("RESULT_TOO_LARGE: too many distribution rows")
    return {"success": True, "result_kind": kind, "rows": rows, "columns": columns,
            "metadata": metadata, "truncated": False}
