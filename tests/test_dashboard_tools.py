"""Transactions and public tools exercised against real dataset adapters."""
from copy import deepcopy
import importlib
from pathlib import Path

import pytest

from refactor_next.backend.analytics import DatasetAdapter, load_dataset

ROOT = Path(__file__).resolve().parents[1]


def classes():
    assert (ROOT / 'backend/dashboard.py').exists(), 'Dashboard implementation missing'
    assert (ROOT / 'backend/tools.py').exists(), 'Toolbox implementation missing'
    return (importlib.import_module('refactor_next.backend.dashboard').Dashboard,
            importlib.import_module('refactor_next.backend.tools').Toolbox)


@pytest.fixture
def stack():
    Dashboard, Toolbox = classes()
    dataset = load_dataset(ROOT / 'datasets/education/interface.py', {})
    dashboard = Dashboard(dataset.description['dataset_id'], dataset.description['version'])
    yield dataset, dashboard, Toolbox(dataset, dashboard)
    dataset.close()


def chart(**changes):
    return {'source': {'tool': 'summarize_learning', 'arguments': {'group_by': 'subject', 'measure': 'mean_score'}},
            'chart_type': 'bar', 'x': 'subject', 'y': 'mean_score', **changes}


def create_committed(dashboard, toolbox):
    draft = dashboard.begin_draft()
    result = toolbox.execute('create_chart', chart(), draft)
    assert result['success'], result
    return dashboard.commit(draft)['views'][0]['id']


def test_private_drafts_defensive_outputs_and_once_only_commit(stack):
    _, dashboard, toolbox = stack
    draft = dashboard.begin_draft()
    assert toolbox.execute('create_chart', chart(), draft)['success']
    assert dashboard.snapshot()['views'] == []
    snapshot = dashboard.commit(draft)
    assert snapshot['dashboard_revision'] == 1
    snapshot['views'].clear()
    draft.document['views'].clear()
    assert len(dashboard.snapshot()['views']) == 1
    with pytest.raises(ValueError):
        dashboard.commit(draft)
    dashboard.discard(draft)
    dashboard.discard(draft)


def test_revision_conflict_and_forged_draft_rejected(stack):
    _, dashboard, toolbox = stack
    stale = dashboard.begin_draft()
    create_committed(dashboard, toolbox)
    assert toolbox.execute('create_chart', chart(), stale)['success']
    with pytest.raises(ValueError):
        dashboard.commit(stale)
    with pytest.raises(ValueError):
        dashboard.commit(deepcopy(dashboard.begin_draft()))
    other = classes()[0]('education', 'wrong').begin_draft()
    with pytest.raises(ValueError):
        dashboard.commit(other)
    assert dashboard.snapshot()['dashboard_revision'] == 1


def test_reads_do_not_increment_revision_and_return_detached_payload(stack):
    dataset, dashboard, toolbox = stack
    draft = dashboard.begin_draft()
    result = toolbox.execute('describe_dataset', {}, draft)
    assert result['payload']['version'] == dataset.description['version']
    read = toolbox.execute('inspect_dashboard', {}, draft)
    read['payload']['views'].append({'bogus': True})
    assert toolbox.execute('summarize_learning', {'group_by': 'subject', 'measure': 'mean_score'}, draft)['success']
    assert not draft.dirty
    assert dashboard.commit(draft)['dashboard_revision'] == 0


def test_tool_effect_category_comes_from_public_and_domain_definitions(stack):
    _, _, toolbox = stack
    assert toolbox.effect_category('describe_dataset') == 'read_only'
    assert toolbox.effect_category('inspect_dashboard') == 'read_only'
    assert toolbox.effect_category('summarize_learning') == 'read_only'
    assert toolbox.effect_category('create_chart') == 'mutating'
    assert toolbox.effect_category('set_analysis_filters') == 'mutating'
    with pytest.raises(ValueError, match='Unknown tool'):
        toolbox.effect_category('not_registered')


def test_undo_cancel_conflict_and_success_do_not_consume_history_early(stack):
    _, dashboard, toolbox = stack
    create_committed(dashboard, toolbox)
    cancelled = dashboard.begin_draft()
    dashboard.stage_undo(cancelled)
    assert cancelled.document['views'] == []
    dashboard.discard(cancelled)
    stale = dashboard.begin_draft()
    dashboard.stage_undo(stale)
    draft = dashboard.begin_draft()
    assert toolbox.execute('highlight_chart', {'view_id': dashboard.snapshot()['views'][0]['id']}, draft)['success']
    dashboard.commit(draft)
    with pytest.raises(ValueError):
        dashboard.commit(stale)
    undo = dashboard.begin_draft()
    assert toolbox.execute('undo_dashboard', {}, undo)['success']
    assert dashboard.commit(undo)['highlighted'] == []
    undo = dashboard.begin_draft()
    dashboard.stage_undo(undo)
    assert dashboard.commit(undo)['views'] == []
    with pytest.raises(ValueError):
        dashboard.stage_undo(dashboard.begin_draft())


def test_undo_is_standalone(stack):
    _, dashboard, toolbox = stack
    view_id = create_committed(dashboard, toolbox)
    draft = dashboard.begin_draft()
    assert toolbox.execute('update_chart', {'view_id': view_id, 'title': 'Updated'}, draft)['success']
    before = deepcopy(draft.document)
    assert not toolbox.execute('undo_dashboard', {}, draft)['success']
    assert draft.document == before
    undo = dashboard.begin_draft()
    assert toolbox.execute('undo_dashboard', {}, undo)['success']
    assert not toolbox.execute('create_chart', chart(), undo)['success']
    assert dashboard.commit(undo)['views'] == []


@pytest.mark.parametrize('change', [
    {'x': 'missing'}, {'y': 'subject'}, {'series': 'missing'}, {'series': 'mean_score'},
    {'chart_type': 'scatter'}, {'chart_type': 'line'},
    {'source': {'tool': 'inspect_dashboard', 'arguments': {}}},
    {'source': {'tool': 'summarize_learning', 'arguments': {'sql': 'SELECT 1'}}},
    {'unexpected': True},
])
def test_invalid_chart_call_restores_exact_draft(stack, change):
    _, dashboard, toolbox = stack
    draft = dashboard.begin_draft()
    before = deepcopy(draft.document)
    result = toolbox.execute('create_chart', chart(**change), draft)
    assert result['success'] is False
    assert isinstance(result['error'], dict)
    assert draft.document == before and draft.dirty is False


def test_update_filter_highlight_delete_legacy_keys_and_metadata(stack):
    _, dashboard, toolbox = stack
    view_id = create_committed(dashboard, toolbox)
    draft = dashboard.begin_draft()
    assert toolbox.execute('update_chart', {'view_id': view_id, 'title': 'Learning'}, draft)['success']
    view = draft.document['views'][0]
    assert view['x_field'] == 'subject' and view['y_field'] == 'mean_score'
    assert view['columns']['mean_score']['unit'] == 'points'
    assert view['source'] == chart()['source']
    assert {'id', 'title', 'chart_type', 'x_field', 'y_field', 'color', 'data', 'columns', 'source', 'highlighted'} <= view.keys()
    assert toolbox.execute('highlight_chart', {'view_id': view_id, 'element': {'subject': 'Math'}, 'dim_others': True}, draft)['success']
    assert draft.document['highlighted'] == [view_id]
    assert draft.document['highlight_element'] == {'subject': 'Math'}
    assert toolbox.execute('set_analysis_filters', {'filters': [{'field': 'cohort', 'op': 'eq', 'value': 'B'}]}, draft)['success']
    assert draft.document['views'][0]['data'] == [{'subject': 'Math', 'mean_score': None}, {'subject': 'Science', 'mean_score': None}]
    assert toolbox.execute('delete_chart', {'view_id': view_id}, draft)['success']
    snapshot = dashboard.commit(draft)
    assert snapshot['views'] == [] and snapshot['highlighted'] == []
    assert snapshot['highlight_element'] is None


@pytest.mark.parametrize('filters', [[{'field': 'nope', 'op': 'eq', 'value': 'A'}],
                                    [{'field': 'cohort', 'op': 'sql', 'value': 'A'}],
                                    [{'field': 'cohort', 'op': 'eq'}],
                                    [{'field': 'cohort', 'op': 'eq', 'value': []}]])
def test_invalid_filter_rejected_even_without_views(stack, filters):
    _, dashboard, toolbox = stack
    draft = dashboard.begin_draft()
    assert not toolbox.execute('set_analysis_filters', {'filters': filters}, draft)['success']
    assert draft.document['filters'] == [] and not draft.dirty


@pytest.mark.parametrize('value', ['not-a-date', '2024-02-30', 42, True, None])
def test_temporal_filter_value_rejected_before_empty_dashboard_commit(stack, value):
    _, dashboard, toolbox = stack
    draft = dashboard.begin_draft()
    result = toolbox.execute('set_analysis_filters', {'filters': [
        {'field': 'assessment_date', 'op': 'gte', 'value': value}]}, draft)
    assert not result['success']
    assert draft.document['filters'] == [] and not draft.dirty
    assert dashboard.commit(draft)['dashboard_revision'] == 0


def test_valid_temporal_filter_on_empty_dashboard_allows_later_chart(stack):
    _, dashboard, toolbox = stack
    draft = dashboard.begin_draft()
    filters = [{'field': 'assessment_date', 'op': 'gte', 'value': '2024-01-01'}]
    assert toolbox.execute('set_analysis_filters', {'filters': filters}, draft)['success']
    assert dashboard.commit(draft)['filters'] == filters
    draft = dashboard.begin_draft()
    assert toolbox.execute('create_chart', chart(), draft)['success']


@pytest.mark.parametrize('value,success', [('ten', False), (True, False), (float('inf'), False), (3.5, True)])
def test_quantitative_filter_validation_uses_resource_metadata(stack, value, success):
    dataset, dashboard, _ = stack
    # Trusted interface descriptors can expose additional shared fields without
    # changing core tool logic; this field already has quantitative metadata.
    class DescribedDataset:
        description = dataset.description
        definitions = dataset.definitions
        execute = dataset.execute
    DescribedDataset.description['filters']['fields'].append('score')
    toolbox = classes()[1](DescribedDataset(), dashboard)
    draft = dashboard.begin_draft()
    result = toolbox.execute('set_analysis_filters', {'filters': [{'field': 'score', 'op': 'gte', 'value': value}]}, draft)
    assert result['success'] is success
    assert draft.dirty is success


def test_scope_reexecution_failure_rolls_back_all_views(stack):
    dataset, dashboard, toolbox = stack
    create_committed(dashboard, toolbox)
    draft = dashboard.begin_draft()
    assert toolbox.execute('create_chart', chart(title='Second'), draft)['success']
    before = deepcopy(draft.document)
    dataset.close()
    assert not toolbox.execute('set_analysis_filters', {'filters': [{'field': 'cohort', 'op': 'eq', 'value': 'A'}]}, draft)['success']
    assert draft.document == before and draft.dirty


def test_schema_registration_collision_and_detachment(stack):
    dataset, dashboard, toolbox = stack
    definitions = toolbox.schemas()
    assert 'summarize_learning' in {d['name'] for d in definitions}
    assert all(set(d) == {'name', 'description', 'parameters'} for d in definitions)
    definitions[0]['parameters'].clear()
    assert toolbox.schemas()[0]['parameters']['type'] == 'object'
    class Collision:
        def describe(self): return {'dataset_id': 'education', 'version': dataset.description['version'], 'description': 'collision'}
        def tool_definitions(self): return [{'name': 'create_chart', 'description': 'collision', 'read_only': True, 'parameters': {'type': 'object'}}]
        def execute(self, name, arguments, scope): raise AssertionError('not called')
        def close(self): pass
    with pytest.raises(ValueError):
        classes()[1](DatasetAdapter(Collision()), dashboard)


def test_temporal_chart_uses_metadata_not_domain_names(stack):
    _, dashboard, toolbox = stack
    draft = dashboard.begin_draft()
    args = chart(source={'tool': 'summarize_learning', 'arguments': {'group_by': 'assessment_date', 'measure': 'mean_score'}}, chart_type='line', x='assessment_date')
    assert toolbox.execute('create_chart', args, draft)['success']
    assert draft.document['views'][0]['columns']['assessment_date']['type'] == 'temporal'


def test_failed_domain_result_remains_wrapped_in_payload(stack):
    dataset, dashboard, toolbox = stack
    dataset.close()
    draft = dashboard.begin_draft()
    result = toolbox.execute('summarize_learning', {'group_by': 'subject', 'measure': 'mean_score'}, draft)
    assert result['success'] is False
    assert result['payload']['success'] is False
    assert result['payload']['dataset_version'] == dataset.description['version']
    assert result['error'] == result['payload']['error']
    assert not draft.dirty


def test_noop_update_and_highlight_clear_do_not_create_revisions(stack):
    _, dashboard, toolbox = stack
    view_id = create_committed(dashboard, toolbox)
    draft = dashboard.begin_draft()
    assert toolbox.execute('update_chart', {'view_id': view_id}, draft)['success']
    assert toolbox.execute('highlight_chart', {'view_id': None}, draft)['success']
    assert dashboard.commit(draft)['dashboard_revision'] == 1


def test_modified_base_and_discarded_drafts_cannot_be_used(stack):
    _, dashboard, toolbox = stack
    draft = dashboard.begin_draft()
    draft.base_revision = 4
    assert not toolbox.execute('create_chart', chart(), draft)['success']
    with pytest.raises(ValueError):
        dashboard.commit(draft)
    dashboard.discard(draft)
    assert not toolbox.execute('inspect_dashboard', {}, draft)['success']


def test_failed_update_keeps_existing_view_and_input_output_are_detached(stack):
    _, dashboard, toolbox = stack
    draft = dashboard.begin_draft()
    args = chart()
    result = toolbox.execute('create_chart', args, draft)
    view_id = result['payload']['id']
    args['source']['arguments']['measure'] = 'student_count'
    result['payload']['data'].clear()
    before = deepcopy(draft.document)
    assert not toolbox.execute('update_chart', {'view_id': view_id, 'y': 'subject'}, draft)['success']
    assert draft.document == before
    assert draft.document['views'][0]['data'] == [{'subject': 'Math', 'mean_score': 75.0}, {'subject': 'Science', 'mean_score': 85.0}]


def test_shared_filters_restore_all_views_after_later_source_schema_drift():
    class ChangingColumns:
        def describe(self):
            return {'dataset_id': 'test', 'version': 'v1', 'description': 'Changing result schema',
                    'filters': {'fields': ['group'], 'operators': ['eq']}}
        def tool_definitions(self):
            return [{'name': 'aggregate', 'description': 'Aggregate', 'read_only': True,
                     'parameters': {'type': 'object', 'properties': {'unstable': {'type': 'boolean'}}, 'required': ['unstable']}}]
        def execute(self, name, arguments, scope):
            metric = 'other' if scope and arguments['unstable'] else 'value'
            return {'success': True, 'dataset_version': 'v1', 'truncated': False,
                    'columns': {'group': {'type': 'nominal'}, metric: {'type': 'quantitative'}},
                    'rows': [{'group': 'A', metric: 2 if scope else 1}]}
        def close(self): pass
    Dashboard, Toolbox = classes()
    dataset = DatasetAdapter(ChangingColumns())
    dashboard = Dashboard('test', 'v1')
    toolbox = Toolbox(dataset, dashboard)
    draft = dashboard.begin_draft()
    for unstable in (False, True):
        args = chart(source={'tool': 'aggregate', 'arguments': {'unstable': unstable}}, x='group', y='value')
        assert toolbox.execute('create_chart', args, draft)['success']
    before = deepcopy(draft.document)
    assert not toolbox.execute('set_analysis_filters', {'filters': [{'field': 'group', 'op': 'eq', 'value': 'A'}]}, draft)['success']
    assert draft.document == before
    assert dashboard.snapshot()['views'] == []


def test_olist_uses_same_create_update_filter_path(tmp_path):
    from refactor_next.tests.test_datasets import write_minimal_olist_csvs
    write_minimal_olist_csvs(tmp_path)
    dataset = load_dataset(ROOT / 'datasets/olist/interface.py', {'data_dir': str(tmp_path)})
    Dashboard, Toolbox = classes()
    dashboard = Dashboard('olist', dataset.description['version'])
    toolbox = Toolbox(dataset, dashboard)
    try:
        draft = dashboard.begin_draft()
        args = chart(source={'tool': 'aggregate', 'arguments': {
            'group_by': ['customer_state'], 'metrics': ['revenue'],
        }}, x='customer_state', y='revenue')
        assert toolbox.execute('create_chart', args, draft)['success']
        view_id = draft.document['views'][0]['id']
        assert toolbox.execute('update_chart', {'view_id': view_id, 'title': 'Revenue'}, draft)['success']
        assert toolbox.execute('set_analysis_filters', {'filters': [{'field': 'customer_state', 'op': 'eq', 'value': 'SP'}]}, draft)['success']
        view = dashboard.commit(draft)['views'][0]
        assert view['data'] == [{'customer_state': 'SP', 'revenue': 30.0}]
        assert view['columns']['revenue']['unit'] == 'BRL'
    finally:
        dataset.close()
