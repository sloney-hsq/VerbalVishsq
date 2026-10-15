"""Read-only Olist visual-analysis smoke paths; no model or external service calls."""
import argparse
import json
from pathlib import Path
from time import perf_counter

from refactor_next.backend.analytics import load_dataset
from refactor_next.backend.dashboard import Dashboard
from refactor_next.backend.tools import Toolbox


ROOT = Path(__file__).resolve().parents[1]


def run_workflows(data_dir, *, export=None):
    dataset = load_dataset(ROOT / 'datasets/olist/interface.py', {'data_dir': str(data_dir)})
    dashboard = Dashboard(dataset.description['dataset_id'], dataset.description['version'])
    tools = Toolbox(dataset, dashboard)
    events = []
    visuals = {}

    def call(name, arguments):
        start = perf_counter()
        draft = dashboard.begin_draft()
        result = tools.execute(name, arguments, draft)
        if not result['success']:
            dashboard.discard(draft)
            raise AssertionError(f'{name}: {result["error"]}')
        document = dashboard.commit(draft)
        payload = result['payload']
        rows = payload.get('data', payload.get('rows', [])) if isinstance(payload, dict) else []
        metadata = payload.get('metadata', {}) if isinstance(payload, dict) else {}
        events.append({'tool': name, 'success': True, 'rows': len(rows),
                       'revision': document['dashboard_revision'],
                       'eligible_count': metadata.get('eligible_count'),
                       'valid_count': metadata.get('valid_count', metadata.get('valid_pair_count')),
                       'sampled': metadata.get('sampling', {}).get('sampled'),
                       'elapsed_ms': round((perf_counter() - start) * 1000, 1)})
        return payload

    def chart(key, tool, arguments, visual):
        view = call('create_chart', {'source': {'tool': tool, 'arguments': arguments},
                                     'visual': visual, 'title': key})
        visuals[key] = view
        assert view['columns'] and view['metadata'].get('observation_unit')
        assert dashboard.snapshot()['active_view_id'] == view['id']
        return view

    try:
        rank = chart('delivery_rank', 'aggregate', {'group_by': ['customer_state'],
            'metrics': ['late_ratio', 'order_count'],
            'having': [{'field': 'order_count', 'op': 'gte', 'value': 1}],
            'top_k': {'dimension': 'customer_state', 'metric': 'order_count', 'k': 10, 'direction': 'desc'}},
            {'type': 'bar', 'encoding': {'x': 'customer_state', 'y': 'late_ratio'},
             'sort': {'field': 'late_ratio', 'direction': 'desc'}})
        assert rank['metadata']['top_k']['ranking_scope'] == 'full_requested_time_range'
        trend = chart('delivery_monthly', 'aggregate', {'group_by': ['order_month', 'customer_state'],
            'metrics': ['late_ratio', 'avg_delivery_days'],
            'limit': 500,
            'filters': [{'field': 'customer_state', 'op': 'in', 'value': ['SP', 'RJ']}],
            'sort': {'field': 'order_month', 'direction': 'asc'}},
            {'type': 'line', 'encoding': {'x': 'order_month', 'y': 'late_ratio', 'color': 'customer_state'}})
        changed = call('update_chart', {'view_id': trend['id'],
            'analysis_patch': {'set': {'group_by': ['order_week', 'customer_state'],
                                       'sort': {'field': 'order_week', 'direction': 'asc'}}},
            'visual_patch': {'set': {'encoding.x': 'order_week'}}})
        assert changed['source']['arguments']['filters'][0]['value'] == ['SP', 'RJ']
        box = chart('delivery_box', 'distribution', {'unit': 'order', 'field': 'delivery_days',
            'output': 'box_summary', 'group_by': 'customer_state',
            'filters': [{'field': 'customer_state', 'op': 'in', 'value': ['SP', 'RJ']}]},
            {'type': 'boxplot', 'encoding': {'x': 'group', 'y': 'delivery_days'}})
        assert box['metadata']['valid_count'] >= 0
        heat = chart('delivery_heatmap', 'aggregate', {'group_by': ['customer_state', 'product_category'],
            'metrics': ['late_ratio'], 'limit': 500,
            'filters': [{'field': 'customer_state', 'op': 'in', 'value': ['SP', 'RJ']}]},
            {'type': 'heatmap', 'encoding': {'x': 'customer_state', 'y': 'product_category', 'color': 'late_ratio'}})
        selected = next(row for row in heat['data'] if row['product_category'] is not None)
        linked = call('set_selection', {'source_view_id': heat['id'], 'source_revision': heat['view_revision'],
            'predicate': [{'field': 'x', 'op': 'eq', 'value': selected['customer_state']},
                          {'field': 'y', 'op': 'eq', 'value': selected['product_category']}],
            'target_view_ids': [box['id']], 'effect': 'filter'})
        assert len(linked['effective_filters']) == 2
        score = chart('rating_composition', 'compare_segments', {'segments': [
            {'id': 'sp', 'label': 'SP', 'filters': [{'field': 'customer_state', 'op': 'eq', 'value': 'SP'}]},
            {'id': 'rj', 'label': 'RJ', 'filters': [{'field': 'customer_state', 'op': 'eq', 'value': 'RJ'}]}],
            'metrics': ['reviewed_order_count'], 'breakdown': 'review_score',
            'normalization': 'within_segment'},
            {'type': 'bar', 'encoding': {'x': 'segment', 'y': 'reviewed_order_count', 'color': 'breakdown'},
             'stack': 'normalize'})
        assert score['columns']['breakdown']['sort_order'] == [1, 2, 3, 4, 5]

        freight = chart('freight_rank', 'aggregate', {'group_by': ['product_category'],
            'metrics': ['avg_freight_ratio'],
            'top_k': {'dimension': 'product_category', 'metric': 'item_count', 'k': 10, 'direction': 'desc'}},
            {'type': 'bar', 'encoding': {'x': 'product_category', 'y': 'avg_freight_ratio'}})
        assert freight['metadata']['top_k']['selected_members']
        histogram = chart('freight_histogram', 'distribution', {'unit': 'item', 'field': 'freight_value',
            'output': 'histogram', 'bins': {'count': 12}},
            {'type': 'histogram', 'encoding': {'x': 'freight_value', 'y': 'count'}})
        assert histogram['metadata']['valid_count'] >= sum(row['count'] for row in histogram['data'])
        scatter = chart('freight_scatter', 'relationship', {'unit': 'item', 'x': 'price',
            'y': 'freight_value', 'representation': 'points', 'sampling': {'max_points': 500, 'seed': 7}},
            {'type': 'scatter', 'encoding': {'x': 'x_value', 'y': 'y_value'}})
        assert scatter['metadata']['sampling']['actual_points'] <= 500
        bins = chart('freight_bins', 'relationship', {'unit': 'item', 'x': 'price',
            'y': 'freight_value', 'representation': 'binned_2d', 'bins': {'x_count': 8, 'y_count': 8}},
            {'type': 'heatmap', 'encoding': {'x': 'x_bin_start', 'y': 'y_bin_start', 'color': 'count'}})
        assert sum(row['count'] for row in bins['data']) == bins['metadata']['valid_pair_count']
        changed = call('update_chart', {'view_id': scatter['id'],
            'analysis_patch': {'set': {'x': 'product_weight_kg'}}})
        assert changed['source']['arguments']['x'] == 'product_weight_kg'
        fork = call('fork_chart', {'view_id': scatter['id'],
            'analysis_patch': {'filter_changes': {'upsert': [
                {'field': 'customer_state', 'op': 'eq', 'value': 'RJ'}]}}})
        assert fork['scope_mode'] == 'snapshot' and fork['source']['arguments']['filters'][0]['value'] == 'RJ'
        fixed = [view['data'] for view in dashboard.snapshot()['views'] if view['id'] in {scatter['id'], fork['id']}]
        call('set_analysis_filters', {'filters': [{'field': 'order_date', 'op': 'gte', 'value': '2017-01-01'}]})
        assert fixed == [view['data'] for view in dashboard.snapshot()['views'] if view['id'] in {scatter['id'], fork['id']}]
        call('undo_dashboard', {})
        assert dashboard.snapshot()['filters'] == []
        if export:
            Path(export).parent.mkdir(parents=True, exist_ok=True)
            Path(export).write_text(json.dumps(visuals, default=str), encoding='utf-8')
        return events, dashboard.snapshot()
    finally:
        dataset.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'datasets/olist/data')
    parser.add_argument('--export', type=Path)
    args = parser.parse_args()
    events, final = run_workflows(args.data_dir, export=args.export)
    print(json.dumps({'steps': events, 'final_revision': final['dashboard_revision']}, indent=2))
