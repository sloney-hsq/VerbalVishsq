"""Explicit chart patch semantics, including stable local filter identities."""
from copy import deepcopy
import uuid


VISUAL_PATHS = {"type", "encoding.x", "encoding.y", "encoding.color", "encoding.size",
                "encoding.facet", "encoding.tooltip", "sort", "stack", "scales.x", "scales.y", "scales.resolve"}


def normalize_source_filters(source):
    source = deepcopy(source)
    filters = source.get("arguments", {}).get("filters", [])
    for item in filters:
        item.setdefault("id", uuid.uuid4().hex)
    return source


def execution_source(source):
    result = deepcopy(source)
    for item in result.get("arguments", {}).get("filters", []):
        item.pop("id", None)
    return result


def apply_analysis_patch(source, patch, filter_ids=None):
    if not isinstance(patch, dict):
        raise ValueError("INVALID_FILTER_VALUE: analysis patch must be object")
    source = deepcopy(source)
    if "replace_source" in patch:
        if set(patch) != {"replace_source", "inherit_scope"} or patch["inherit_scope"] is not True:
            raise ValueError("INVALID_FILTER_VALUE: replace_source requires inherit_scope only")
        replacement = deepcopy(patch["replace_source"])
        previous = source.get("arguments", {})
        arguments = replacement.setdefault("arguments", {})
        previous_filters = previous.get("filters", [])
        replacement_filters = arguments.get("filters", [])
        replacement_fields = {item["field"] for item in replacement_filters}
        if previous_filters or replacement_filters:
            arguments["filters"] = [*deepcopy([item for item in previous_filters if item["field"] not in replacement_fields]),
                                    *deepcopy(replacement_filters)]
        if "time_range" not in arguments and "time_range" in previous:
            arguments["time_range"] = deepcopy(previous["time_range"])
        return normalize_source_filters(replacement)
    if set(patch) - {"set", "unset", "filter_changes"}:
        raise ValueError("INVALID_FILTER_VALUE: unsupported analysis patch")
    arguments = source["arguments"]
    set_values, unset = patch.get("set", {}), patch.get("unset", [])
    if not isinstance(set_values, dict) or not isinstance(unset, list) or any(key in unset for key in set_values):
        raise ValueError("INVALID_FILTER_VALUE: conflicting analysis paths")
    for key in unset:
        if key not in arguments or key in {"group_by", "metrics", "segments", "unit", "field", "x", "y", "output", "representation"}:
            raise ValueError("INVALID_FILTER_VALUE: cannot unset required or absent parameter")
        del arguments[key]
    arguments.update(deepcopy(set_values))
    changes = patch.get("filter_changes")
    if changes is not None:
        if not isinstance(changes, dict) or set(changes) - {"upsert", "remove"}:
            raise ValueError("INVALID_FILTER_VALUE: invalid filter changes")
        filters = arguments.setdefault("filters", [])
        by_id = {item["id"]: index for index, item in enumerate(filters)}
        for filter_id in changes.get("remove", []):
            if filter_id not in by_id:
                raise ValueError("INVALID_FILTER_VALUE: unknown filter ID")
            filters = [item for item in filters if item["id"] != filter_id]
        by_id = {item["id"]: index for index, item in enumerate(filters)}
        for item in changes.get("upsert", []):
            item = deepcopy(item)
            item.setdefault("id", uuid.uuid4().hex)
            if item["id"] in by_id:
                filters[by_id[item["id"]]] = item
            else:
                filters.append(item)
        arguments["filters"] = filters
    return normalize_source_filters(source)


def apply_visual_patch(visual, patch):
    if not isinstance(patch, dict) or set(patch) - {"set", "unset"}:
        raise ValueError("INCOMPATIBLE_ENCODING: invalid visual patch")
    visual = deepcopy(visual)
    set_values, unset = patch.get("set", {}), patch.get("unset", [])
    if not isinstance(set_values, dict) or not isinstance(unset, list) or any(key in unset for key in set_values):
        raise ValueError("INCOMPATIBLE_ENCODING: conflicting visual paths")
    for path in [*unset, *set_values]:
        if path not in VISUAL_PATHS:
            raise ValueError("INCOMPATIBLE_ENCODING: unsupported visual path")
    for path in unset:
        target = visual
        parts = path.split(".")
        for part in parts[:-1]:
            target = target.get(part, {})
        target.pop(parts[-1], None)
    for path, value in set_values.items():
        target = visual
        parts = path.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = deepcopy(value)
    return visual
