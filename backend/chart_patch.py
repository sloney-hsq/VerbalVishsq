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
        if item.get("op") == "or":
            for branch in item.get("branches", []):
                for leaf in branch.get("all", []):
                    leaf.setdefault("id", uuid.uuid4().hex)
    return source


def execution_source(source):
    result = deepcopy(source)
    def strip(item):
        item.pop("id", None)
        for branch in item.get("branches", []):
            for leaf in branch.get("all", []):
                strip(leaf)
    for item in result.get("arguments", {}).get("filters", []):
        strip(item)
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
        replacement_fields = {item["field"] for item in replacement_filters if "field" in item}
        replacement_ids = {item.get("id") for item in replacement_filters if item.get("op") == "or"}
        if previous_filters or replacement_filters:
            arguments["filters"] = [*deepcopy([item for item in previous_filters
                if (item.get("field") not in replacement_fields if "field" in item else item.get("id") not in replacement_ids)]),
                                    *deepcopy(replacement_filters)]
        if "time_range" not in arguments and "time_range" in previous:
            arguments["time_range"] = deepcopy(previous["time_range"])
        return normalize_source_filters(replacement)
    if set(patch) - {"set", "unset", "filter_changes", "measure_changes"}:
        raise ValueError("INVALID_FILTER_VALUE: unsupported analysis patch")
    arguments = source["arguments"]
    set_values, unset = patch.get("set", {}), patch.get("unset", [])
    if not isinstance(set_values, dict) or not isinstance(unset, list) or any(key in unset for key in set_values):
        raise ValueError("INVALID_FILTER_VALUE: conflicting analysis paths")
    for key in unset:
        if key not in arguments:
            raise ValueError("INVALID_FILTER_VALUE: cannot unset required or absent parameter")
        del arguments[key]
    arguments.update(deepcopy(set_values))
    changes = patch.get("filter_changes")
    if changes is not None:
        if not isinstance(changes, dict) or set(changes) - {"upsert", "remove"}:
            raise ValueError("INVALID_FILTER_VALUE: invalid filter changes")
        filters = arguments.setdefault("filters", [])
        if len({item["id"] for item in filters}) != len(filters):
            raise ValueError("INVALID_FILTER_VALUE: duplicate filter IDs")
        by_id = {item["id"]: index for index, item in enumerate(filters)}
        if len(set(changes.get("remove", []))) != len(changes.get("remove", [])):
            raise ValueError("INVALID_FILTER_VALUE: duplicate remove IDs")
        for filter_id in changes.get("remove", []):
            if filter_id not in by_id:
                raise ValueError("INVALID_FILTER_VALUE: unknown filter ID")
            filters = [item for item in filters if item["id"] != filter_id]
        by_id = {item["id"]: index for index, item in enumerate(filters)}
        upserts = changes.get("upsert", [])
        explicit_ids = [item["id"] for item in upserts if "id" in item]
        if len(set(explicit_ids)) != len(explicit_ids) or set(explicit_ids) & set(changes.get("remove", [])):
            raise ValueError("INVALID_FILTER_VALUE: duplicate or conflicting filter edits")
        for item in upserts:
            item = deepcopy(item)
            item.setdefault("id", uuid.uuid4().hex)
            if item["id"] in by_id:
                filters[by_id[item["id"]]] = item
            else:
                filters.append(item)
        arguments["filters"] = filters
    changes = patch.get("measure_changes")
    if changes is not None:
        if "measures" in set_values or not isinstance(changes, dict) or set(changes) - {"upsert", "remove"}:
            raise ValueError("INVALID_MEASURE: invalid measure changes")
        measures = deepcopy(arguments.get("measures", []))
        by_id = {item.get("id"): index for index, item in enumerate(measures)}
        remove = changes.get("remove", [])
        upserts = changes.get("upsert", [])
        ids = [item.get("id") for item in upserts]
        if len(set(remove)) != len(remove) or any(mid not in by_id for mid in remove) or len(set(ids)) != len(ids) or set(remove) & set(ids):
            raise ValueError("INVALID_MEASURE: conflicting measure changes")
        measures = [item for item in measures if item.get("id") not in remove]
        by_id = {item["id"]: index for index, item in enumerate(measures)}
        for item in upserts:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise ValueError("INVALID_MEASURE: measure upsert requires id")
            if item["id"] in by_id:
                measures[by_id[item["id"]]] = deepcopy(item)
            else:
                measures.append(deepcopy(item))
        arguments["measures"] = measures
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
