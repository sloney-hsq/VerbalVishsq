"""The visible ordinal and model context must refer to the same view ID."""
from copy import deepcopy

from refactor_next.backend.provider_payload import dashboard_context


def test_model_context_numbers_left_views_before_category_matrix_without_mutating_state():
    state = {'dashboard_revision': 8, 'views': [
        {'id': 'a', 'chart_type': 'bar'},
        {'id': 'matrix', 'chart_type': 'heatmap'},
        {'id': 'bins', 'chart_type': 'heatmap', 'result_kind': 'binned_2d'},
        {'id': 'b', 'chart_type': 'line'},
    ]}
    before = deepcopy(state)
    projected = dashboard_context(state)
    assert {v['id']: v.get('display_number') for v in projected['views']} == {
        'a': 1, 'bins': 2, 'b': 3, 'matrix': 4,
    }
    assert state == before
