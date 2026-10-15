"""Typed chart edits, source scope and analysis history."""
from copy import deepcopy

from test_dashboard_tools import stack, chart  # noqa: F401


def _create(toolbox, dashboard, payload):
    draft = dashboard.begin_draft()
    result = toolbox.execute("create_chart", payload, draft)
    assert result["success"], result
    return dashboard.commit(draft)["views"][-1]


def test_legacy_chart_and_typed_source(stack):
    _, dashboard, toolbox = stack
    old = _create(toolbox, dashboard, chart())
    assert old["visual"]["type"] == "bar"
    typed = _create(toolbox, dashboard, {"source": chart()["source"],
        "visual": {"type": "bar", "encoding": {"x": "subject", "y": "mean_score"}}})
    assert typed["result_kind"] == "table" and typed["view_revision"] == 1
    draft = dashboard.begin_draft()
    invalid = toolbox.execute("create_chart", {"source": {"tool": "inspect_dashboard", "arguments": {}},
        "visual": {"type": "bar", "encoding": {"x": "subject", "y": "mean_score"}}}, draft)
    assert not invalid["success"] and len(draft.document["views"]) == 2


def test_visual_only_update_does_not_query(stack):
    dataset, dashboard, _ = stack
    class Counted:
        description, definitions = dataset.description, dataset.definitions
        calls = 0
        def execute(self, *args):
            self.calls += 1
            return dataset.execute(*args)
    from refactor_next.backend.tools import Toolbox
    counted = Counted()
    toolbox = Toolbox(counted, dashboard)
    view = _create(toolbox, dashboard, chart())
    assert counted.calls == 1
    draft = dashboard.begin_draft()
    result = toolbox.execute("update_chart", {"view_id": view["id"], "title": "Edited",
        "visual_patch": {"set": {"sort": {"field": "mean_score", "direction": "desc"}}}}, draft)
    assert result["success"], result
    assert counted.calls == 1
    assert result["payload"]["view_revision"] == 2
    dashboard.commit(draft)


def test_patch_preserves_unmentioned_source_arguments(stack):
    _, dashboard, toolbox = stack
    source = chart()["source"]
    source["arguments"]["filters"] = [{"field": "cohort", "op": "eq", "value": "A"}]
    view = _create(toolbox, dashboard, {"source": source, "visual": {"type": "bar", "encoding": {"x": "subject", "y": "mean_score"}}})
    draft = dashboard.begin_draft()
    result = toolbox.execute("update_chart", {"view_id": view["id"],
        "analysis_patch": {"set": {"measure": "mean_score"}}}, draft)
    assert result["success"], result
    assert result["payload"]["source"]["arguments"]["filters"][0]["field"] == "cohort"
    filter_id = result["payload"]["source"]["arguments"]["filters"][0]["id"]
    before = deepcopy(draft.document)
    invalid = toolbox.execute("update_chart", {"view_id": view["id"],
        "analysis_patch": {"filter_changes": {"remove": ["missing-id"]}}}, draft)
    assert not invalid["success"] and draft.document == before and filter_id


def test_switch_to_box_requires_distribution(stack):
    _, dashboard, toolbox = stack
    view = _create(toolbox, dashboard, chart())
    draft = dashboard.begin_draft()
    result = toolbox.execute("update_chart", {"view_id": view["id"],
        "visual_patch": {"set": {"type": "boxplot"}}}, draft)
    assert not result["success"] and draft.document["views"][0]["view_revision"] == 1


def test_fork_scope_and_noop_revision(stack):
    _, dashboard, toolbox = stack
    view = _create(toolbox, dashboard, chart())
    draft = dashboard.begin_draft()
    assert toolbox.execute("set_analysis_filters", {"filters": [{"field": "cohort", "op": "eq", "value": "A"}]}, draft)["success"]
    dashboard.commit(draft)
    draft = dashboard.begin_draft()
    result = toolbox.execute("fork_chart", {"view_id": view["id"], "title": "RJ baseline"}, draft)
    assert result["success"], result
    assert len(draft.document["views"]) == 2
    assert all(item["scope_mode"] == "snapshot" for item in draft.document["views"])
    assert draft.document["views"][0]["scope_filters"] == [{"field": "cohort", "op": "eq", "value": "A"}]
    dashboard.commit(draft)
    draft = dashboard.begin_draft()
    before = deepcopy(draft.document)
    noop = toolbox.execute("update_chart", {"view_id": view["id"], "title": view["title"]}, draft)
    assert noop["success"] and draft.document == before


def test_linked_fork_from_snapshot_requeries_current_scope(stack):
    _, dashboard, toolbox = stack
    original = _create(toolbox, dashboard, chart())
    draft = dashboard.begin_draft()
    assert toolbox.execute("set_analysis_filters", {"filters": [{"field": "cohort", "op": "eq", "value": "A"}]}, draft)["success"]
    dashboard.commit(draft)
    draft = dashboard.begin_draft()
    assert toolbox.execute("fork_chart", {"view_id": original["id"]}, draft)["success"]
    dashboard.commit(draft)
    draft = dashboard.begin_draft()
    assert toolbox.execute("set_analysis_filters", {"filters": [{"field": "cohort", "op": "eq", "value": "B"}]}, draft)["success"]
    dashboard.commit(draft)
    draft = dashboard.begin_draft()
    linked = toolbox.execute("fork_chart", {"view_id": original["id"], "scope_mode": "linked"}, draft)
    assert linked["success"], linked
    assert linked["payload"]["data"] == [
        {"subject": "Math", "mean_score": None}, {"subject": "Science", "mean_score": None}]
    assert linked["payload"]["scope_mode"] == "linked"


def test_replace_source_inherits_unrelated_local_scope():
    from refactor_next.backend.chart_patch import apply_analysis_patch
    source = {"tool": "distribution", "arguments": {"unit": "item", "field": "price", "output": "box_summary",
        "filters": [{"id": "region", "field": "customer_state", "op": "eq", "value": "SP"}],
        "time_range": {"field": "order_date", "start": "2017-01-01", "end": "2018-01-01"}}}
    replacement = {"tool": "relationship", "arguments": {"unit": "item", "x": "product_weight_kg", "y": "freight_value",
        "representation": "points", "filters": [{"field": "product_weight_kg", "op": "lt", "value": 3}]}}
    output = apply_analysis_patch(source, {"replace_source": replacement, "inherit_scope": True}, {})
    assert {f["field"] for f in output["arguments"]["filters"]} == {"customer_state", "product_weight_kg"}
    assert output["arguments"]["time_range"] == source["arguments"]["time_range"]


def test_public_schema_exposes_visual_and_patch_contract(stack):
    _, dashboard, toolbox = stack
    schemas = {entry['name']: entry['parameters'] for entry in toolbox.schemas()}
    assert schemas['create_chart']['properties']['visual']['properties']['type']['enum'] == [
        'bar', 'line', 'scatter', 'heatmap', 'histogram', 'boxplot']
    assert schemas['update_chart']['properties']['analysis_patch']['oneOf'][1]['properties']['replace_source']['oneOf']
    draft = dashboard.begin_draft()
    bad = toolbox.execute('create_chart', {**chart(), 'visual': {'type': 'nonsense', 'encoding': {}}}, draft)
    assert not bad['success'] and bad['error']['path'] == ['visual', 'type']
    bad = toolbox.execute('update_chart', {'view_id': 'any', 'visual_patch': {'set': {'strange.path': 1}}}, draft)
    assert not bad['success'] and bad['error']['path'] == ['visual_patch', 'set']


def test_undo_revision_is_nonreusable_for_stale_selection(stack):
    _, dashboard, toolbox = stack
    view = _create(toolbox, dashboard, chart())
    draft = dashboard.begin_draft()
    assert toolbox.execute('update_chart', {'view_id': view['id'], 'title': 'A'}, draft)['success']
    dashboard.commit(draft)
    draft = dashboard.begin_draft()
    assert toolbox.execute('undo_dashboard', {}, draft)['success']
    restored = dashboard.commit(draft)['views'][0]
    assert restored['view_revision'] > 2
    draft = dashboard.begin_draft()
    assert toolbox.execute('update_chart', {'view_id': view['id'], 'title': 'B'}, draft)['success']
    assert draft.document['views'][0]['view_revision'] > restored['view_revision']
    stale = toolbox.execute('set_selection', {'source_view_id': view['id'], 'source_revision': 2,
        'predicate': [{'field': 'subject', 'op': 'eq', 'value': 'Math'}],
        'target_view_ids': ['not-a-target'], 'effect': 'filter'}, draft)
    assert not stale['success'] and stale['error']['code'] == 'STALE_SOURCE_VIEW'


def test_non_olist_field_registry_validation(stack):
    dataset, dashboard, _ = stack
    class Registered:
        definitions = dataset.definitions
        description = {**dataset.description, 'field_index': {
            'cohort': {'type': 'nominal', 'groupable': True, 'allowed_ops': ['eq', 'in']}}}
        def execute(self, *args):
            return dataset.execute(*args)
    toolbox = __import__('refactor_next.backend.tools', fromlist=['Toolbox']).Toolbox(Registered(), dashboard)
    draft = dashboard.begin_draft()
    bad = toolbox.execute('set_analysis_filters', {'filters': [{'field': 'cohort', 'op': 'eq', 'value': 4}]}, draft)
    assert not bad['success'] and bad['error']['code'] == 'INVALID_FILTER_VALUE'
    good = toolbox.execute('set_analysis_filters', {'filters': [{'field': 'cohort', 'op': 'eq', 'value': 'A'}]}, draft)
    assert good['success']


def test_visual_contract_uses_metadata_for_stack_color_and_log():
    from refactor_next.backend.chart_contract import validate_visual
    result = {"result_kind": "aggregate", "rows": [{"category": "A", "value": 2, "color": 3}],
        "columns": {"category": {"type": "nominal"}, "value": {"type": "quantitative", "additive": False},
                    "color": {"type": "quantitative"}}, "metadata": {}}
    import pytest
    with pytest.raises(ValueError):
        validate_visual({"type": "bar", "encoding": {"x": "category", "y": "value", "color": "category"}, "stack": "zero"}, result)
    assert validate_visual({"type": "scatter", "encoding": {"x": "value", "y": "color", "color": "color"}}, result)["type"] == "scatter"
    assert validate_visual({"type": "bar", "encoding": {"x": "value", "y": "category"}}, result)["type"] == "bar"
    with pytest.raises(ValueError):
        validate_visual({"type": "bar", "encoding": {"x": "category", "y": "value"}, "scales": {"x": "log"}}, result)


def test_histogram_log_checks_real_bin_values():
    from refactor_next.backend.chart_contract import validate_visual
    import pytest
    result = {"result_kind": "histogram", "rows": [{"bin_start": 0, "bin_end": 1, "count": 2, "proportion": 1}],
        "columns": {name: {"type": "quantitative"} for name in ("bin_start", "bin_end", "count", "proportion")},
        "metadata": {"field": "delivery_days"}}
    with pytest.raises(ValueError):
        validate_visual({"type": "histogram", "encoding": {"x": "delivery_days", "y": "count"}, "scales": {"x": "log"}}, result)
