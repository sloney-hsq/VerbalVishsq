"""Explicit one-shot cross-view selection semantics."""
from pathlib import Path

from refactor_next.backend.analytics import load_dataset
from refactor_next.backend.dashboard import Dashboard
from refactor_next.backend.tools import Toolbox
from test_olist_adapter import olist_csvs  # noqa: F401


def _stack(data_dir):
    interface = Path(__file__).resolve().parents[1] / 'datasets' / 'olist' / 'interface.py'
    dataset = load_dataset(interface, {'data_dir': str(data_dir)})
    dashboard = Dashboard(dataset.description['dataset_id'], dataset.description['version'])
    return dataset, dashboard, Toolbox(dataset, dashboard)


def _create(toolbox, draft, source, visual):
    result = toolbox.execute('create_chart', {'source': source, 'visual': visual}, draft)
    assert result['success'], result
    return result['payload']['id']


def test_heatmap_cell_filters_target_and_clear_preserves_local_scope(olist_csvs):
    ds, dashboard, toolbox = _stack(olist_csvs)
    try:
        draft = dashboard.begin_draft()
        source = _create(toolbox, draft,
            {'tool': 'aggregate', 'arguments': {'group_by': ['customer_state', 'product_category'], 'metrics': ['late_ratio']}},
            {'type': 'heatmap', 'encoding': {'x': 'customer_state', 'y': 'product_category', 'color': 'late_ratio'}})
        target = _create(toolbox, draft,
            {'tool': 'distribution', 'arguments': {'unit': 'order', 'field': 'delivery_days', 'output': 'box_summary',
                'filters': [{'field': 'customer_state', 'op': 'eq', 'value': 'SP'}]}},
            {'type': 'boxplot', 'encoding': {'y': 'delivery_days'}})
        dashboard.commit(draft)
        draft = dashboard.begin_draft()
        revision = next(v['view_revision'] for v in draft.document['views'] if v['id'] == source)
        result = toolbox.execute('set_selection', {'source_view_id': source, 'source_revision': revision,
            'predicate': [{'field': 'customer_state', 'op': 'eq', 'value': 'SP'},
                          {'field': 'product_category', 'op': 'eq', 'value': 'books'}],
            'target_view_ids': [target], 'effect': 'filter'}, draft)
        assert result['success'], result
        target_view = next(v for v in draft.document['views'] if v['id'] == target)
        assert {f['field'] for f in target_view['metadata']['effective_filters']} >= {'customer_state', 'product_category'}
        assert target_view['source']['arguments']['filters'][0]['field'] == 'customer_state'
        dashboard.commit(draft)
        draft = dashboard.begin_draft()
        cleared = toolbox.execute('set_selection', {'source_view_id': source, 'source_revision': revision,
            'target_view_ids': [target], 'effect': 'clear'}, draft)
        assert cleared['success'], cleared
        assert source not in next(v for v in draft.document['views'] if v['id'] == target)['selection_filters']
    finally:
        ds.close()


def test_stale_or_nonmatching_selection_rejects_all_targets(olist_csvs):
    ds, dashboard, toolbox = _stack(olist_csvs)
    try:
        draft = dashboard.begin_draft()
        source = _create(toolbox, draft,
            {'tool': 'aggregate', 'arguments': {'group_by': ['customer_state'], 'metrics': ['order_count']}},
            {'type': 'bar', 'encoding': {'x': 'customer_state', 'y': 'order_count'}})
        target = _create(toolbox, draft,
            {'tool': 'distribution', 'arguments': {'unit': 'order', 'field': 'delivery_days', 'output': 'box_summary'}},
            {'type': 'boxplot', 'encoding': {'y': 'delivery_days'}})
        dashboard.commit(draft)
        draft = dashboard.begin_draft()
        assert toolbox.execute('update_chart', {'view_id': source, 'title': 'New title'}, draft)['success']
        before = draft.document['views'][-1]['data'][:]
        stale = toolbox.execute('set_selection', {'source_view_id': source, 'source_revision': 1,
            'predicate': [{'field': 'customer_state', 'op': 'eq', 'value': 'SP'}],
            'target_view_ids': [target], 'effect': 'filter'}, draft)
        assert not stale['success'] and stale['error']['code'] == 'STALE_SOURCE_VIEW'
        invalid = toolbox.execute('set_selection', {'source_view_id': source, 'source_revision': 2,
            'predicate': [{'field': 'customer_state', 'op': 'eq', 'value': 'ZZ'}],
            'target_view_ids': [target], 'effect': 'filter'}, draft)
        assert not invalid['success'] and invalid['error']['code'] == 'INVALID_SELECTION'
        assert draft.document['views'][-1]['data'] == before
    finally:
        ds.close()


def test_last_2d_bin_maps_both_axes_to_inclusive_raw_ranges(olist_csvs):
    ds, dashboard, toolbox = _stack(olist_csvs)
    try:
        draft = dashboard.begin_draft()
        source = _create(toolbox, draft,
            {'tool': 'relationship', 'arguments': {'unit': 'item', 'x': 'price', 'y': 'freight_value',
                'representation': 'binned_2d', 'bins': {'x_count': 2, 'y_count': 2}}},
            {'type': 'heatmap', 'encoding': {'x': 'x_bin_start', 'y': 'y_bin_start', 'color': 'count'}})
        target = _create(toolbox, draft,
            {'tool': 'aggregate', 'arguments': {'group_by': ['customer_state'], 'metrics': ['item_count']}},
            {'type': 'bar', 'encoding': {'x': 'customer_state', 'y': 'item_count'}})
        source_view = next(view for view in draft.document['views'] if view['id'] == source)
        max_row = source_view['data'][-1]
        result = toolbox.execute('set_selection', {'source_view_id': source,
            'source_revision': source_view['view_revision'],
            'predicate': [{'field': 'x', 'op': 'eq', 'value': max_row['x_bin_start']},
                          {'field': 'y', 'op': 'eq', 'value': max_row['y_bin_start']}],
            'target_view_ids': [target], 'effect': 'filter'}, draft)
        assert result['success'], result
        raw = result['payload']['effective_filters']
        assert {(item['field'], item['op']) for item in raw} == {
            ('price', 'gte'), ('price', 'lte'), ('freight_value', 'gte'), ('freight_value', 'lte')}
        assert next(view for view in draft.document['views'] if view['id'] == target)['metadata']['effective_filters']
    finally:
        ds.close()


def test_highlight_accepts_displayed_aggregate_measure_but_filter_rejects_it(olist_csvs):
    ds, dashboard, toolbox = _stack(olist_csvs)
    try:
        draft = dashboard.begin_draft()
        source = _create(toolbox, draft,
            {'tool': 'aggregate', 'arguments': {'group_by': ['customer_state'], 'metrics': ['order_count']}},
            {'type': 'bar', 'encoding': {'x': 'customer_state', 'y': 'order_count'}})
        target = _create(toolbox, draft,
            {'tool': 'aggregate', 'arguments': {'group_by': ['customer_state'], 'metrics': ['order_count']}},
            {'type': 'bar', 'encoding': {'x': 'customer_state', 'y': 'order_count'}})
        source_view = next(view for view in draft.document['views'] if view['id'] == source)
        value = source_view['data'][0]['order_count']
        args = {'source_view_id': source, 'source_revision': 1,
                'predicate': [{'field': 'y', 'op': 'eq', 'value': value}],
                'target_view_ids': [target]}
        highlighted = toolbox.execute('set_selection', {**args, 'effect': 'highlight'}, draft)
        assert highlighted['success'], highlighted
        rejected = toolbox.execute('set_selection', {**args, 'effect': 'filter'}, draft)
        assert not rejected['success'] and rejected['error']['code'] == 'INVALID_SELECTION'
    finally:
        ds.close()


def test_dynamic_aggregate_measure_is_highlightable_but_never_a_raw_filter(olist_csvs):
    ds, dashboard, toolbox = _stack(olist_csvs)
    try:
        draft = dashboard.begin_draft()
        source = _create(toolbox, draft,
            {'tool': 'aggregate', 'arguments': {'group_by': ['customer_state'], 'metrics': [], 'unit': 'order',
                'measures': [{'id': 'delivery_p90', 'stat': 'quantile', 'field': 'delivery_days', 'q': .9}]}},
            {'type': 'bar', 'encoding': {'x': 'customer_state', 'y': 'delivery_p90'}})
        target = _create(toolbox, draft,
            {'tool': 'aggregate', 'arguments': {'group_by': ['customer_state'], 'metrics': [], 'unit': 'order',
                'measures': [{'id': 'delivery_p90', 'stat': 'quantile', 'field': 'delivery_days', 'q': .9}]}},
            {'type': 'bar', 'encoding': {'x': 'customer_state', 'y': 'delivery_p90'}})
        source_view = next(view for view in draft.document['views'] if view['id'] == source)
        selected_row = next(row for row in source_view['data'] if row['delivery_p90'] is not None)
        args = {'source_view_id': source, 'source_revision': source_view['view_revision'],
                'predicate': [{'field': 'y', 'op': 'eq', 'value': selected_row['delivery_p90']}],
                'target_view_ids': [target]}
        highlighted = toolbox.execute('set_selection', {**args, 'effect': 'highlight'}, draft)
        assert highlighted['success'], highlighted
        rejected = toolbox.execute('set_selection', {**args, 'effect': 'filter'}, draft)
        assert not rejected['success'] and rejected['error']['code'] == 'INVALID_SELECTION'
    finally:
        ds.close()


def test_month_bucket_selection_uses_half_open_raw_date_range(olist_csvs):
    ds, dashboard, toolbox = _stack(olist_csvs)
    try:
        draft = dashboard.begin_draft()
        source = _create(toolbox, draft,
            {'tool': 'aggregate', 'arguments': {'group_by': ['order_month'], 'metrics': ['order_count']}},
            {'type': 'line', 'encoding': {'x': 'order_month', 'y': 'order_count'}})
        target = _create(toolbox, draft,
            {'tool': 'aggregate', 'arguments': {'group_by': ['customer_state'], 'metrics': ['order_count']}},
            {'type': 'bar', 'encoding': {'x': 'customer_state', 'y': 'order_count'}})
        source_view = next(view for view in draft.document['views'] if view['id'] == source)
        month = source_view['data'][0]['order_month']
        result = toolbox.execute('set_selection', {'source_view_id': source, 'source_revision': 1,
            'predicate': [{'field': 'x', 'op': 'eq', 'value': month}],
            'target_view_ids': [target], 'effect': 'filter'}, draft)
        assert result['success'], result
        filters = result['payload']['effective_filters']
        assert [item['op'] for item in filters] == ['gte', 'lt']
        assert all(item['field'] == 'order_date' for item in filters)
        assert filters[0]['value'] < filters[1]['value']
    finally:
        ds.close()


def test_snapshot_fork_materializes_selection_and_deleted_source_can_be_cleared(olist_csvs):
    ds, dashboard, toolbox = _stack(olist_csvs)
    try:
        draft = dashboard.begin_draft()
        source = _create(toolbox, draft,
            {'tool': 'aggregate', 'arguments': {'group_by': ['customer_state'], 'metrics': ['order_count']}},
            {'type': 'bar', 'encoding': {'x': 'customer_state', 'y': 'order_count'}})
        target = _create(toolbox, draft,
            {'tool': 'aggregate', 'arguments': {'group_by': ['customer_state'], 'metrics': ['order_count']}},
            {'type': 'bar', 'encoding': {'x': 'customer_state', 'y': 'order_count'}})
        linked = _create(toolbox, draft,
            {'tool': 'aggregate', 'arguments': {'group_by': ['customer_state'], 'metrics': ['order_count']}},
            {'type': 'bar', 'encoding': {'x': 'customer_state', 'y': 'order_count'}})
        selected = toolbox.execute('set_selection', {'source_view_id': source, 'source_revision': 1,
            'predicate': [{'field': 'x', 'op': 'eq', 'value': 'SP'}],
            'target_view_ids': [target, linked], 'effect': 'filter'}, draft)
        assert selected['success'], selected
        fork = toolbox.execute('fork_chart', {'view_id': target}, draft)
        assert fork['success'], fork
        assert {'field': 'customer_state', 'op': 'eq', 'value': 'SP'} in fork['payload']['scope_filters']
        assert fork['payload']['selection_filters'] == {}
        assert toolbox.execute('delete_chart', {'view_id': source}, draft)['success']
        linked_view = next(view for view in draft.document['views'] if view['id'] == linked)
        assert linked_view['selection_source_status'][source] == 'source_removed'
        cleared = toolbox.execute('set_selection', {'source_view_id': source, 'source_revision': 1,
            'target_view_ids': [linked], 'effect': 'clear'}, draft)
        assert cleared['success'], cleared
        linked_view = next(view for view in draft.document['views'] if view['id'] == linked)
        assert source not in linked_view['selection_filters']
    finally:
        ds.close()
