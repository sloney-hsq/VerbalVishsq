"""Explicit two-period summary and aligned calendar series."""
from datetime import date, timedelta
import calendar


def _parse(value):
    try: return date.fromisoformat(value)
    except (TypeError, ValueError) as exc: raise ValueError("INCOMPATIBLE_PERIODS: boundaries must be ISO dates") from exc


def _advance(value, grain):
    if grain == "day": return value + timedelta(days=1)
    if grain == "week": return value + timedelta(days=7)
    year, month = value.year + (value.month == 12), value.month % 12 + 1
    return date(year, month, 1)


def _buckets(period, grain):
    start, end = _parse(period["start"]), _parse(period["end"])
    if grain == "week" and (start.weekday() or end.weekday()) or grain == "month" and (start.day != 1 or end.day != 1):
        raise ValueError("INCOMPATIBLE_PERIODS: series boundaries are not calendar aligned")
    values, cursor = [], start
    while cursor < end:
        nxt = _advance(cursor, grain)
        if nxt > end: raise ValueError("INCOMPATIBLE_PERIODS: partial final bucket")
        values.append((cursor, nxt)); cursor = nxt
    return values


def _window(con, args, scope, start, end, registry):
    group_by = args.get("group_by", [])
    if isinstance(group_by, str): group_by = [group_by]
    filters = args.get("filters", [])
    rows, columns, meta = [], {}, {"metric_valid_counts": {}}
    valid_by_key = {}
    if args.get("metrics"):
        query_args = {"group_by": group_by, "metrics": args["metrics"], "filters": filters,
                      "time_range": {"field": args["time_field"], "start": start, "end": end}, "limit": 1_000_000}
        sql, params, names, limit = registry["queries"].build_aggregate(query_args, scope, registry["fields"], registry["metrics"], include_valid_counts=True)
        fetched = con.execute(sql, params).fetchall()
        if len(fetched) > limit:
            raise ValueError("RESULT_TOO_LARGE: period grouping exceeds one million rows")
        for raw in fetched:
            mapped = dict(zip(names, raw)); counts = {}
            for metric in args["metrics"]: counts[metric] = mapped.pop("__valid_" + metric)
            rows.append(mapped)
            key = tuple(mapped.get(g) for g in group_by)
            valid_by_key.setdefault(key, {}).update(counts)
            for metric, count in counts.items():
                meta["metric_valid_counts"].setdefault(metric, {})[str(key)] = count
        columns.update(registry["columns"]([*group_by, *args["metrics"]]))
    if args.get("measures"):
        measured_args = {"unit": args["unit"], "group_by": group_by, "metrics": [], "measures": args["measures"],
                         "filters": filters, "time_range": {"field": args["time_field"], "start": start, "end": end},
                         "limit": 1_000_000}
        measured = registry["measure_queries"].execute(con, measured_args, scope,
            {"fields": registry["fields"], "predicate": registry["predicate"]})
        if measured["truncated"]:
            raise ValueError("RESULT_TOO_LARGE: period grouping exceeds one million rows")
        for index, row in enumerate(measured["rows"]):
            key = tuple(row.get(g) for g in group_by)
            if index < len(measured["metadata"].get("row_valid_counts", [])):
                valid_by_key.setdefault(key, {}).update(measured["metadata"]["row_valid_counts"][index])
        meta.update(measured["metadata"])
        if rows:
            index = {tuple(row.get(g) for g in group_by): row for row in rows}
            for row in measured["rows"]: index.setdefault(tuple(row.get(g) for g in group_by), {}).update(row)
            rows = list(index.values())
        else: rows = measured["rows"]
        columns.update(measured["columns"])
    sql, params, _ = registry["predicate"].observation_sql(args.get("unit", "order"), [], group_by,
        [*(scope or []), *filters], {"field": args["time_field"], "start": start, "end": end}, registry["fields"])
    observations = con.execute(sql, params).fetchall()
    counts = {}
    for obs in observations:
        key = tuple(obs[1:]); counts[key] = counts.get(key, 0) + 1
    if not rows and not group_by: rows = [{}]
    for row in rows:
        row["record_count"] = counts.get(tuple(row.get(g) for g in group_by), 0)
    meta["row_valid_counts"] = [valid_by_key.get(tuple(row.get(g) for g in group_by), {}) for row in rows]
    columns["record_count"] = {"type": "quantitative", "unit": "observations"}
    return rows, columns, meta


def execute(con, arguments, scope, registry):
    periods = arguments["periods"]
    if len(periods) != 2 or len({p["id"] for p in periods}) != 2:
        raise ValueError("INCOMPATIBLE_PERIODS: exactly two unique periods are required")
    parsed = [(_parse(p["start"]), _parse(p["end"])) for p in periods]
    if any(start >= end for start, end in parsed) or max(parsed[0][0], parsed[1][0]) < min(parsed[0][1], parsed[1][1]):
        raise ValueError("INCOMPATIBLE_PERIODS: periods must be nonempty and nonoverlapping")
    output, grain = arguments["output"], arguments.get("grain")
    work_arguments, work_scope, pooled_rules = dict(arguments), scope, []
    if any(item.get("op") == "quantile_between" for item in arguments.get("filters", []) if isinstance(item, dict)):
        common = [*(scope or []), *arguments.get("filters", [])]
        contexts = [(common, {"field": arguments["time_field"], "start": p["start"], "end": p["end"]}) for p in periods]
        resolved, pooled_rules = registry["measure_queries"].resolve_quantile_contexts(con, arguments["unit"], contexts,
            {"fields": registry["fields"], "predicate": registry["predicate"]}, base_filters=common)
        work_arguments["filters"], work_scope = resolved, []
    if output == "series" and grain not in {"day", "week", "month"}:
        raise ValueError("INCOMPATIBLE_PERIODS: series requires day, week or month grain")
    bucket_sets = [_buckets(p, grain) if output == "series" else [(s, e)] for p, (s, e) in zip(periods, parsed)]
    if output == "series" and len(bucket_sets[0]) != len(bucket_sets[1]):
        raise ValueError("INCOMPATIBLE_PERIODS: series periods need equal bucket counts")
    rows, data_columns, coverage = [], {}, []
    group_by = arguments.get("group_by", []); group_by = [group_by] if isinstance(group_by, str) else group_by
    requested_metrics = [*arguments.get("metrics", []), *[m["id"] for m in arguments.get("measures", [])]]
    extent = con.execute("SELECT MIN(order_date), MAX(order_date) FROM order_grain").fetchone()
    if extent[0] is None or extent[1] is None:
        raise ValueError("EMPTY_REFERENCE_POPULATION: dataset has no observed order dates")
    extent_start, extent_end = extent[0], extent[1] + timedelta(days=1)
    scope_lower = scope_upper = None; ambiguous_date_scope = False
    for item in (scope or []):
        if not isinstance(item, dict): continue
        if item.get("op") == "or":
            if any(leaf.get("field") == arguments["time_field"] for branch in item.get("branches", []) for leaf in branch.get("all", [])):
                ambiguous_date_scope = True
            continue
        if item.get("field") != arguments["time_field"]: continue
        op, value = item.get("op"), item.get("value")
        if op in {"gte", "gt", "eq"}:
            boundary = _parse(str(value)[:10]) + (timedelta(days=1) if op == "gt" else timedelta())
            scope_lower = max(scope_lower, boundary) if scope_lower else boundary
        if op in {"lt", "lte", "eq"}:
            boundary = _parse(str(value)[:10]) + (timedelta(days=1) if op in {"lte", "eq"} else timedelta())
            scope_upper = min(scope_upper, boundary) if scope_upper else boundary
        if op == "between" and isinstance(value, list) and len(value) == 2:
            lo, hi = _parse(str(value[0])[:10]), _parse(str(value[1])[:10]) + timedelta(days=1)
            scope_lower = max(scope_lower, lo) if scope_lower else lo
            scope_upper = min(scope_upper, hi) if scope_upper else hi
        if op not in {"gte", "gt", "lt", "lte", "eq", "between"}: ambiguous_date_scope = True
    effective_boundaries, scope_clipped, within_extent = {}, {}, {}
    for period, (start, end) in zip(periods, parsed):
        effective_start = max(start, scope_lower) if scope_lower else start
        effective_end = min(end, scope_upper) if scope_upper else end
        effective_boundaries[period["id"]] = {"start": effective_start.isoformat(), "end": effective_end.isoformat()}
        scope_clipped[period["id"]] = ambiguous_date_scope or effective_start != start or effective_end != end
        within_extent[period["id"]] = start >= extent_start and end <= extent_end
    comparable = {p["id"]: within_extent[p["id"]] and not scope_clipped[p["id"]] for p in periods}
    for period, buckets in zip(periods, bucket_sets):
        present_indexes = set()
        for index, (start, end) in enumerate(buckets):
            values, columns, window_meta = _window(con, work_arguments, work_scope, start.isoformat(), end.isoformat(), registry)
            data_columns.update(columns)
            for value_index, value in enumerate(values):
                record_count = value.pop("record_count")
                row = {"period_id": period["id"], "period": period["label"],
                       "__valid_meta": (window_meta.get("row_valid_counts", [{}] * len(values))[value_index]
                                          if value_index < len(window_meta.get("row_valid_counts", [])) else {})}
                if output == "series":
                    row.update(bucket_index=index, bucket_start=start.isoformat(), bucket_end=end.isoformat(),
                               bucket_present=record_count > 0)
                row.update(value); row["record_count"] = record_count
                if not record_count:
                    for name in [*arguments.get("metrics", []), *[m["id"] for m in arguments.get("measures", [])]]: row[name] = None
                else: present_indexes.add(index)
                rows.append(row)
        coverage.append({"period_id": period["id"], "duration_days": (parsed[len(coverage)][1] - parsed[len(coverage)][0]).days,
                         "requested_bucket_count": len(buckets), "buckets_with_observations": len(present_indexes),
                         "within_observed_date_extent": within_extent[period["id"]],
                         "effective_requested_boundary": effective_boundaries[period["id"]],
                         "shared_date_scope_clipped": scope_clipped[period["id"]]})
    # Complete the group × period × bucket spine from the observed domain across both periods.
    if group_by:
        domain = {tuple(row.get(g) for g in group_by) for row in rows}
        existing = {(row["period_id"], row.get("bucket_index", 0), tuple(row.get(g) for g in group_by)) for row in rows}
        for period, buckets in zip(periods, bucket_sets):
            for index, (start, end) in enumerate(buckets):
                for group in domain:
                    key = (period["id"], index, group)
                    if key in existing: continue
                    row = {"period_id": period["id"], "period": period["label"], "__valid_meta": {}, **dict(zip(group_by, group)),
                           **{name: None for name in requested_metrics}, "record_count": 0}
                    if output == "series": row.update(bucket_index=index, bucket_start=start.isoformat(), bucket_end=end.isoformat(), bucket_present=False)
                    rows.append(row)
    comparison = arguments.get("comparison")
    if comparison:
        refid = comparison["reference_period_id"]
        if refid not in {p["id"] for p in periods}: raise ValueError("INVALID_COMPARISON: unknown reference period")
        metrics = requested_metrics
        keys = [*group_by, *( ["bucket_index"] if output == "series" else [])]
        refs = {tuple(row.get(k) for k in keys): row for row in rows if row["period_id"] == refid}
        ratio_ids = {m["id"] for m in arguments.get("measures", []) if m["stat"] in {"threshold_ratio", "registered_ratio"}}
        ratio_ids |= {m for m in arguments.get("metrics", []) if registry["metrics"][m]["unit"] == "ratio"}
        for metric in metrics:
            if "percentage_point_difference" in comparison["outputs"] and metric not in ratio_ids:
                raise ValueError("INVALID_COMPARISON: percentage points require ratio")
            for output_name in comparison["outputs"]:
                data_columns[metric + "__" + output_name] = {"type": "quantitative", "unit": "percentage_points" if output_name == "percentage_point_difference" else "ratio" if output_name == "relative_difference" else data_columns[metric].get("unit")}
        for row in rows:
            ref = refs.get(tuple(row.get(k) for k in keys))
            for metric in metrics:
                value, reference = row.get(metric), ref.get(metric) if ref else None
                if not comparable.get(row["period_id"]) or not comparable.get(refid):
                    value = reference = None
                diff = value - reference if value is not None and reference is not None else None
                if "difference" in comparison["outputs"]: row[metric + "__difference"] = diff
                if "relative_difference" in comparison["outputs"]: row[metric + "__relative_difference"] = diff / abs(reference) if diff is not None and reference else None
                if "percentage_point_difference" in comparison["outputs"]: row[metric + "__percentage_point_difference"] = 100 * diff if diff is not None else None
    columns = {"period_id": {"type": "nominal"}, "period": {"type": "nominal"}}
    if output == "series": columns.update(bucket_index={"type": "ordinal"}, bucket_start={"type": "temporal"}, bucket_end={"type": "temporal"}, bucket_present={"type": "nominal"})
    columns.update(data_columns)
    warnings = ["Observation density is not proof of collection completeness or fair exposure."]
    if output == "summary" and coverage[0]["duration_days"] != coverage[1]["duration_days"]:
        warnings.append("Summary periods have unequal exposure durations; totals are not automatically rate-normalized.")
    if not all(within_extent.values()):
        warnings.append("At least one requested period extends outside the observed date extent; comparison deltas are null.")
    if any(scope_clipped.values()):
        warnings.append("Shared date filters clip or ambiguously intersect at least one requested period; comparison deltas are null.")
    row_valid_counts = [row.pop("__valid_meta", {}) for row in rows]
    return {"success": True, "result_kind": "periods", "rows": rows, "columns": columns, "truncated": False,
        "metadata": {"observation_unit": arguments.get("unit", "order"), "output": output, "grain": grain,
                     "calendar_boundary": "[start,end)", "observed_date_extent": [extent[0], extent[1]], "periods": coverage,
                     "measure_definitions": {m["id"]: m for m in arguments.get("measures", [])},
                     "row_valid_counts": row_valid_counts,
                     "quantile_rules": pooled_rules,
                     "comparison_suppressed_reasons": ([*([] if all(within_extent.values()) else ["outside_observed_date_extent"]),
                         *([] if not any(scope_clipped.values()) else ["shared_date_filter"])]),
                     "warnings": warnings}}
