"""Typed analysis boundary tests."""
import pytest

from refactor_next.backend.analytics import DatasetAdapter
from refactor_next.datasets.olist.query_common import normalize_filters, compile_filters
from refactor_next.datasets.olist.schema import FIELD_INDEX
from refactor_next.datasets.olist.metrics import METRIC_INDEX


def test_filter_types_and_boundaries():
    values = normalize_filters([{"field": "customer_state", "op": "in", "value": ["SP", "RJ"]}], FIELD_INDEX)
    assert compile_filters(values, FIELD_INDEX) == (['"customer_state" IN (?, ?)'], ["SP", "RJ"])
    for bad in ([{"field": "customer_state", "op": "in", "value": "SP"}],
                [{"field": "price", "op": "gte", "value": True}],
                [{"field": "order_date", "op": "eq", "value": "not-a-date"}]):
        with pytest.raises(ValueError):
            normalize_filters(bad, FIELD_INDEX)
    assert compile_filters(normalize_filters([{"field": "price", "op": "between", "value": [1, 2]}], FIELD_INDEX), FIELD_INDEX) == (['"price" BETWEEN ? AND ?'], [1, 2])


def test_observation_registry():
    assert "order" not in FIELD_INDEX["product_weight_kg"]["observation_units"]
    assert "item" in FIELD_INDEX["product_weight_kg"]["observation_units"]
    assert {"reviewed_order_count", "valid_delivery_order_count", "late_eligible_order_count"} <= METRIC_INDEX.keys()


class _ResultInterface:
    def __init__(self, result):
        self.result = result
    def describe(self):
        return {"dataset_id": "test", "version": "1", "description": "test"}
    def tool_definitions(self):
        return [{"name": "query", "description": "query", "read_only": True, "parameters": {"type": "object"}}]
    def execute(self, name, arguments, scope):
        return self.result
    def close(self):
        pass


def test_result_contract_legacy_and_typed():
    base = {"success": True, "dataset_version": "1", "rows": [{"x": 1}], "columns": {"x": {"type": "quantitative"}}, "truncated": False}
    assert DatasetAdapter(_ResultInterface(base)).execute("query", {})["success"]
    malformed = {**base, "result_kind": "box_summary", "metadata": {}}
    assert not DatasetAdapter(_ResultInterface(malformed)).execute("query", {})["success"]
    nonfinite = {**base, "rows": [{"x": float("inf")}]}
    assert not DatasetAdapter(_ResultInterface(nonfinite)).execute("query", {})["success"]
