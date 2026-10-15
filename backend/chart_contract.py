"""Dataset-neutral typed chart contract and legacy normalization."""
from copy import deepcopy
from math import isfinite


TYPES = {"bar", "line", "scatter", "heatmap", "histogram", "boxplot"}
CHANNELS = {"x", "y", "color", "size", "facet", "tooltip"}


def normalize_visual(config):
    if "visual" in config:
        if any(key in config for key in ("chart_type", "x", "y", "series")):
            raise ValueError("INCOMPATIBLE_ENCODING: mixed legacy and typed visual arguments")
        visual = deepcopy(config["visual"])
    else:
        visual = {"type": config["chart_type"], "encoding": {"x": config["x"], "y": config["y"]}}
        if config.get("series") is not None:
            visual["encoding"]["color"] = config["series"]
    if not isinstance(visual, dict) or visual.get("type") not in TYPES or not isinstance(visual.get("encoding"), dict):
        raise ValueError("INCOMPATIBLE_ENCODING: invalid visual specification")
    if set(visual) - {"type", "encoding", "stack", "sort", "scales"} or set(visual["encoding"]) - CHANNELS:
        raise ValueError("INCOMPATIBLE_ENCODING: unsupported visual property")
    return visual


def validate_visual(visual, result):
    visual = deepcopy(visual)
    kind = result.get("result_kind", "table")
    columns = result["columns"]
    encoding = visual["encoding"]
    chart_type = visual["type"]
    if kind == "table" and chart_type not in {"bar", "line", "scatter"}:
        raise ValueError("INCOMPATIBLE_ENCODING: legacy table supports bar, line or scatter")
    if chart_type == "histogram" and kind != "histogram" or chart_type == "boxplot" and kind != "box_summary":
        raise ValueError("INCOMPATIBLE_ENCODING: chart requires matching distribution result")
    if chart_type == "heatmap" and kind not in {"aggregate", "segments", "binned_2d"}:
        raise ValueError("INCOMPATIBLE_ENCODING: heatmap requires two dimensions")
    for channel, field in encoding.items():
        values = field if channel == "tooltip" else [field]
        if channel == "tooltip" and not isinstance(values, list):
            raise ValueError("INCOMPATIBLE_ENCODING: tooltip must be an array")
        for name in values:
            if not isinstance(name, str) or (name not in columns and not (chart_type in {"histogram", "boxplot"} and name == result.get("metadata", {}).get("field"))):
                raise ValueError("INCOMPATIBLE_ENCODING: chart encoding references missing result field")
    x, y = encoding.get("x"), encoding.get("y")
    if chart_type in {"bar", "line", "scatter", "heatmap", "histogram"} and (not x or not y):
        raise ValueError("INCOMPATIBLE_ENCODING: chart requires x and y")
    typ = lambda name: columns.get(name, {}).get("type")
    if chart_type == "bar" and not ((typ(x) in {"nominal", "ordinal", "temporal"} and typ(y) == "quantitative") or
                                    (typ(y) in {"nominal", "ordinal", "temporal"} and typ(x) == "quantitative")):
        raise ValueError("INCOMPATIBLE_ENCODING: bar requires category and measure")
    if chart_type == "line" and not (typ(x) in {"temporal", "ordinal", "quantitative"} and typ(y) == "quantitative"):
        raise ValueError("INCOMPATIBLE_ENCODING: line requires ordered x and measure")
    if chart_type == "scatter" and not (typ(x) == "quantitative" and typ(y) == "quantitative"):
        raise ValueError("INCOMPATIBLE_ENCODING: scatter requires numeric axes")
    if chart_type == "heatmap" and not (typ(x) in {"nominal", "ordinal", "temporal", "quantitative"} and
                                          typ(y) in {"nominal", "ordinal", "temporal", "quantitative"} and
                                          typ(encoding.get("color")) == "quantitative"):
        raise ValueError("INCOMPATIBLE_ENCODING: heatmap requires numeric color")
    if chart_type in {"bar", "line"} and encoding.get("color") and typ(encoding["color"]) not in {"nominal", "ordinal"}:
        raise ValueError("INCOMPATIBLE_ENCODING: grouped color must be discrete")
    if chart_type == "histogram" and not (x in {"bin_start", result.get("metadata", {}).get("field")} and y in {"count", "proportion"}):
        raise ValueError("INCOMPATIBLE_ENCODING: histogram uses bins and count/proportion")
    if chart_type == "boxplot" and y not in {None, result.get("metadata", {}).get("field"), "median"}:
        raise ValueError("INCOMPATIBLE_ENCODING: boxplot uses summary quartiles")
    for channel in ("color", "facet"):
        field = encoding.get(channel)
        if field and channel == "facet" and typ(field) not in {"nominal", "ordinal"}:
            raise ValueError("INCOMPATIBLE_ENCODING: facet requires discrete field")
        if field and channel == "facet" and len({row.get(field) for row in result["rows"]}) > 12:
            raise ValueError("RESULT_TOO_LARGE: over 12 facet panels")
    size = encoding.get("size")
    if size:
        if chart_type != "scatter" or typ(size) != "quantitative" or any(row.get(size) is not None and row[size] < 0 for row in result["rows"]):
            raise ValueError("INCOMPATIBLE_ENCODING: size requires nonnegative scatter measure")
    stack = visual.get("stack", "none")
    if stack not in {"none", "zero", "normalize"} or stack != "none" and (chart_type != "bar" or not encoding.get("color")):
        raise ValueError("INCOMPATIBLE_ENCODING: invalid stack")
    if stack != "none":
        measure = y if typ(y) == "quantitative" else x
        metadata = columns[measure]
        if stack == "zero" and not (metadata.get("additive") is True or metadata.get("already_normalized") is True):
            raise ValueError("INCOMPATIBLE_ENCODING: stacking requires declared additive measure")
        if stack == "normalize" and not (metadata.get("additive") is True and result.get("metadata", {}).get("composition_complete") is True
                                         and result.get("metadata", {}).get("segment_denominator")):
            raise ValueError("INCOMPATIBLE_ENCODING: normalized stack needs complete composition and denominator")
    sort = visual.get("sort")
    if sort is not None and (not isinstance(sort, dict) or set(sort) != {"field", "direction"} or sort["field"] not in columns or sort["direction"] not in {"asc", "desc"}):
        raise ValueError("INCOMPATIBLE_ENCODING: invalid sort")
    scales = visual.get("scales", {})
    if not isinstance(scales, dict) or set(scales) - {"x", "y", "resolve"} or scales.get("resolve", "shared") not in {"shared", "independent"}:
        raise ValueError("INCOMPATIBLE_ENCODING: invalid scales")
    for channel in ("x", "y"):
        scale = scales.get(channel, "linear")
        if scale not in {"linear", "log"}:
            raise ValueError("INCOMPATIBLE_ENCODING: invalid axis scale")
        if scale == "log":
            field = encoding.get(channel)
            if field is None or typ(field) not in {None, "quantitative"}:
                raise ValueError("INCOMPATIBLE_ENCODING: log scale requires quantitative axis")
            check_fields = [field]
            if chart_type == "histogram" and field == result.get("metadata", {}).get("field"):
                check_fields = ["bin_start", "bin_end"]
            if chart_type == "boxplot" and field == result.get("metadata", {}).get("field"):
                check_fields = ["whisker_low", "q1", "median", "q3", "whisker_high"]
            if any(row.get(name) is not None and row[name] <= 0 for row in result["rows"] for name in check_fields):
                raise ValueError("INCOMPATIBLE_ENCODING: log scale requires positive values")
    return visual
