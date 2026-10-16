"""Paired numeric observations and complete-data density grids."""
from bisect import bisect_right
from collections import defaultdict
import hashlib
import math

from refactor_next.datasets.olist.distributions import bin_edges


def _pearson(xs, ys):
    if len(xs) < 2:
        return None, "fewer_than_two_pairs"
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    dx, dy = [x - mx for x in xs], [y - my for y in ys]
    denom = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    return (sum(a * b for a, b in zip(dx, dy)) / denom, None) if denom else (None, "zero_variance")


def _ranks(values):
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        rank = (i + 1 + j) / 2
        for k in range(i, j): ranks[order[k]] = rank
        i = j
    return ranks


def _statistics(rows, requested):
    xs, ys = [row[1] for row in rows], [row[2] for row in rows]
    result = {"valid_pair_count": len(rows)}
    for name in requested:
        value, reason = _pearson(xs, ys) if name == "pearson" else _pearson(_ranks(xs), _ranks(ys))
        result[name] = value
        if reason: result[name + "_reason"] = reason
    if len(rows) < 30: result["warning"] = "small_sample"
    return result


def execute_relationship(con, arguments, scope, registry):
    unit, x, y = arguments["unit"], arguments["x"], arguments["y"]
    group_by = arguments.get("group_by")
    if isinstance(group_by, list):
        if len(group_by) > 1:
            raise ValueError("INCOMPATIBLE_GRAIN: relationship supports one group")
        group_by = group_by[0] if group_by else None
    representation = arguments.get("representation", "points")
    if representation not in {"points", "binned_2d", "summary"}:
        raise ValueError("INVALID_FILTER_VALUE: invalid representation")
    if (representation == "binned_2d" and "sampling" in arguments or representation == "points" and "bins" in arguments
            or representation == "summary" and any(key in arguments for key in ("sampling", "bins"))):
        raise ValueError("INVALID_FILTER_VALUE: sampling and bins are exclusive")
    common = registry["common"]
    requested_filters = [*(scope or []), *arguments.get("filters", [])]
    effective, default_applied = common.effective_filters(requested_filters, registry["fields"])
    sql, params = common.observation_query(unit, [x, y], group_by, requested_filters, arguments.get("time_range"), registry["fields"])
    fetched = con.execute(sql, params).fetchall()
    valid = [row for row in fetched if row[1] is not None and row[2] is not None and math.isfinite(row[1]) and math.isfinite(row[2])]
    groups = {row[3] if group_by else None for row in fetched}
    if len(groups) > 12:
        raise ValueError("RESULT_TOO_LARGE: relationship has over 12 groups")
    group_counts = {str(group): {"eligible_count": sum(1 for row in fetched if (row[3] if group_by else None) == group),
                                 "valid_pair_count": sum(1 for row in valid if (row[3] if group_by else None) == group)} for group in groups}
    metadata = {"observation_unit": unit, "x": x, "y": y, "group_by": group_by,
                "eligible_count": len(fetched), "valid_pair_count": len(valid), "missing_pair_count": len(fetched) - len(valid),
                "group_counts": group_counts, "effective_filters": effective,
                "default_scope_applied": default_applied, "time_range": arguments.get("time_range"),
                "overlaps_across_groups": bool(unit == "order" and group_by and registry["fields"][group_by]["grain"] == "item")}
    requested = arguments.get("correlations", [])
    if not isinstance(requested, list) or len(set(requested)) != len(requested) or any(x not in {"pearson", "spearman"} for x in requested):
        raise ValueError("INVALID_FILTER_VALUE: invalid correlations")
    overall_pairs = list({row[0]: row for row in valid}.values())
    metadata["correlations"] = {"overall": _statistics(overall_pairs, requested), "by_group": {
        str(group): _statistics([row for row in valid if (row[3] if group_by else None) == group], requested)
        for group in groups}}
    if representation == "summary":
        rows = []
        for group in sorted(groups, key=lambda value: str(value)):
            eligible = [row for row in fetched if (row[3] if group_by else None) == group]
            paired = [row for row in valid if (row[3] if group_by else None) == group]
            stats = _statistics(paired, requested)
            row = {"valid_pair_count": len(paired), "missing_pair_count": len(eligible) - len(paired),
                   **{name: stats[name] for name in requested}}
            if group_by: row["group"] = group
            rows.append(row)
        columns = {"valid_pair_count": {"type": "quantitative", "unit": "observations"},
                   "missing_pair_count": {"type": "quantitative", "unit": "observations"},
                   **{name: {"type": "quantitative", "unit": "correlation"} for name in requested}}
        kind = "relationship_summary"
    elif representation == "points":
        sampling = arguments.get("sampling", {})
        if not isinstance(sampling, dict) or set(sampling) - {"max_points", "seed"}:
            raise ValueError("INVALID_FILTER_VALUE: invalid sampling")
        max_points = sampling.get("max_points", 2000)
        seed = sampling.get("seed", 0)
        if type(max_points) is not int or not 1 <= max_points <= 5000 or type(seed) is not int:
            raise ValueError("INVALID_FILTER_VALUE: invalid sampling budget or seed")
        selected = sorted(valid, key=lambda row: hashlib.sha256(f"{seed}:{row[0]}:{row[3] if group_by else ''}".encode()).digest())[:max_points]
        rows = [{"observation_id": row[0], "x_value": row[1], "y_value": row[2], **({"group": row[3]} if group_by else {})} for row in selected]
        columns = {"observation_id": {"type": "nominal"}, "x_value": {"type": "quantitative", "source_field": x, "unit": registry["fields"][x]["unit"]},
                   "y_value": {"type": "quantitative", "source_field": y, "unit": registry["fields"][y]["unit"]}}
        metadata["sampling"] = {"method": "sha256_observation_key", "seed": seed,
                                "actual_points": len(rows), "sampled": len(valid) > len(rows)}
        kind = "points"
    else:
        bins = arguments.get("bins", {"x_count": 20, "y_count": 20})
        if not isinstance(bins, dict) or set(bins) - {"x_count", "y_count"}:
            raise ValueError("INVALID_FILTER_VALUE: invalid 2D bins")
        nx, ny = bins.get("x_count", 20), bins.get("y_count", 20)
        if type(nx) is not int or type(ny) is not int or not 1 <= nx <= 50 or not 1 <= ny <= 50:
            raise ValueError("INVALID_FILTER_VALUE: invalid 2D bin counts")
        x_edges = bin_edges([row[1] for row in valid], {"count": nx})
        y_edges = bin_edges([row[2] for row in valid], {"count": ny})
        counts = defaultdict(int)
        for row in valid:
            group = row[3] if group_by else None
            xi = min(bisect_right(x_edges, row[1]) - 1, len(x_edges) - 2)
            yi = min(bisect_right(y_edges, row[2]) - 1, len(y_edges) - 2)
            counts[(group, xi, yi)] += 1
        rows = []
        for group in sorted(groups, key=lambda value: str(value)):
            for xi in range(max(0, len(x_edges) - 1)):
                for yi in range(max(0, len(y_edges) - 1)):
                    rows.append({"x_bin_start": x_edges[xi], "x_bin_end": x_edges[xi + 1],
                                 "y_bin_start": y_edges[yi], "y_bin_end": y_edges[yi + 1],
                                 "count": counts[(group, xi, yi)], **({"group": group} if group_by else {})})
        columns = {name: {"type": "quantitative", "source_field": x if name.startswith("x_") else y,
                          "unit": registry["fields"][x if name.startswith("x_") else y]["unit"]}
                   for name in ("x_bin_start", "x_bin_end", "y_bin_start", "y_bin_end")}
        columns["count"] = {"type": "quantitative", "unit": "observations"}
        metadata["bins"] = {"x_edges": x_edges, "y_edges": y_edges, "complete_data": True}
        kind = "binned_2d"
    if group_by:
        columns["group"] = {"type": registry["fields"][group_by]["type"], "source_field": group_by}
    return {"success": True, "result_kind": kind, "rows": rows, "columns": columns,
            "metadata": metadata, "truncated": False}
