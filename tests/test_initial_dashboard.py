import json
from pathlib import Path

import pytest

from refactor_next.backend.dashboard import Dashboard
from refactor_next.backend.analytics import load_dataset
from refactor_next.backend.realtime import AnalysisSession, InitialDashboardError
from refactor_next.backend.tools import Toolbox
from refactor_next.backend.trace import Trace


ROOT = Path(__file__).resolve().parents[1]


class Dataset:
    description = {
        'dataset_id': 'initial-dashboard-test',
        'version': 'v1',
        'description': 'Initial dashboard test dataset',
    }
    definitions = [{
        'name': 'aggregate',
        'description': 'Return a deterministic aggregate.',
        'read_only': True,
        'parameters': {
            'type': 'object',
            'properties': {
                'group_by': {'type': 'string'},
                'metric': {'type': 'string'},
            },
            'required': ['group_by', 'metric'],
            'additionalProperties': False,
        },
    }]

    def execute(self, name, arguments, scope):
        if arguments['metric'] == 'fail':
            return {
                'success': False,
                'dataset_version': 'v1',
                'error': {'code': 'dataset_error', 'message': 'synthetic materialization failed'},
            }
        group_by, metric = arguments['group_by'], arguments['metric']
        return {
            'success': True,
            'dataset_version': 'v1',
            'rows': [{group_by: 'A', metric: 1}],
            'columns': {
                group_by: {'type': 'nominal', 'label': group_by},
                metric: {'type': 'quantitative', 'label': metric, 'unit': 'count'},
            },
            'truncated': False,
        }


class TrackingDashboard(Dashboard):
    def __init__(self):
        super().__init__('initial-dashboard-test', 'v1')
        self.begun = []
        self.committed = []
        self.discarded = []

    def begin_draft(self):
        draft = super().begin_draft()
        self.begun.append(draft)
        return draft

    def commit(self, draft):
        self.committed.append(draft)
        return super().commit(draft)

    def discard(self, draft):
        self.discarded.append(draft)
        return super().discard(draft)


class TrackingToolbox(Toolbox):
    def __init__(self, dataset, dashboard):
        super().__init__(dataset, dashboard)
        self.executions = []

    def execute(self, name, args, draft):
        self.executions.append((name, draft))
        return super().execute(name, args, draft)


async def send(_event):
    pass


def chart(index, *, metric=None):
    metric = metric or f'metric_{index}'
    return {
        'source': {'tool': 'aggregate', 'arguments': {'group_by': f'group_{index}', 'metric': metric}},
        'chart_type': 'bar',
        'x': f'group_{index}',
        'y': metric,
        'title': f'Chart {index}',
    }


def build_session(initial_dashboard=None):
    dataset = Dataset()
    dashboard = TrackingDashboard()
    toolbox = TrackingToolbox(dataset, dashboard)
    session = AnalysisSession(
        dataset,
        send,
        send,
        'revision_enabled',
        Trace(),
        dashboard=dashboard,
        toolbox=toolbox,
        initial_dashboard=initial_dashboard,
    )
    return session, dashboard, toolbox


def test_olist_config_uses_ignored_repo_local_data_directory():
    settings = json.loads((ROOT / 'configs' / 'olist.json').read_text(encoding='utf-8'))
    data_dir = settings['dataset']['data_dir']
    ignored_paths = {
        line.strip()
        for line in (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    }

    assert data_dir == 'datasets/olist/data'
    assert '..' not in Path(data_dir).parts
    assert 'datasets/olist/data/' in ignored_paths


def test_no_initial_dashboard_preserves_empty_revision_zero():
    session, dashboard, toolbox = build_session()

    assert dashboard.snapshot()['dashboard_revision'] == 0
    assert dashboard.snapshot()['views'] == []
    assert dashboard.begun == []
    assert toolbox.executions == []
    session.trace.close()


def test_five_initial_views_use_one_draft_and_one_commit():
    configured = [chart(index) for index in range(5)]

    session, dashboard, toolbox = build_session(configured)

    snapshot = dashboard.snapshot()
    assert snapshot['dashboard_revision'] == 1
    assert [view['title'] for view in snapshot['views']] == [f'Chart {index}' for index in range(5)]
    assert len(dashboard.begun) == 1
    assert dashboard.committed == dashboard.begun
    assert dashboard.discarded == []
    assert [name for name, _draft in toolbox.executions] == ['create_chart'] * 5
    assert {id(draft) for _name, draft in toolbox.executions} == {id(dashboard.begun[0])}
    session.trace.close()


def test_initial_view_failure_discards_entire_private_draft():
    dataset = Dataset()
    dashboard = TrackingDashboard()
    toolbox = TrackingToolbox(dataset, dashboard)

    with pytest.raises(InitialDashboardError, match='Initial dashboard view 3.*synthetic materialization failed'):
        AnalysisSession(
            dataset,
            send,
            send,
            'revision_enabled',
            Trace(),
            dashboard=dashboard,
            toolbox=toolbox,
            initial_dashboard=[chart(0), chart(1), chart(2, metric='fail'), chart(3)],
        )

    assert dashboard.snapshot()['dashboard_revision'] == 0
    assert dashboard.snapshot()['views'] == []
    assert dashboard.committed == []
    assert dashboard.discarded == dashboard.begun
    assert [name for name, _draft in toolbox.executions] == ['create_chart'] * 3


def test_olist_initial_dashboard_is_five_formal_aggregate_chart_requests():
    settings = json.loads((ROOT / 'configs' / 'olist.json').read_text(encoding='utf-8'))
    configured = settings['initial_dashboard']

    assert [view['title'] for view in configured] == [
        'Monthly Orders Trend',
        'Average Review Score by State',
        'Orders by State',
        'Category Revenue (Top 15)',
        'Monthly Average Delivery Days',
    ]
    assert [(view['chart_type'], view['x'], view['y']) for view in configured] == [
        ('line', 'order_month', 'order_count'),
        ('bar', 'customer_state', 'avg_review_score'),
        ('bar', 'customer_state', 'order_count'),
        ('bar', 'product_category', 'revenue'),
        ('line', 'order_month', 'avg_delivery_days'),
    ]
    assert len(configured) == 5
    assert all(view['source']['tool'] == 'aggregate' for view in configured)
    assert [(view['source']['arguments']['group_by'], view['source']['arguments']['metrics']) for view in configured] == [
        (['order_month'], ['order_count']),
        (['customer_state'], ['avg_review_score']),
        (['customer_state'], ['order_count']),
        (['product_category'], ['revenue']),
        (['order_month'], ['avg_delivery_days']),
    ]
    assert not any(key == 'rows' for view in configured for key in _nested_keys(view))
    assert [view['source']['arguments']['sort'] for view in configured] == [
        {'field': 'order_month', 'direction': 'asc'},
        {'field': 'avg_review_score', 'direction': 'desc'},
        {'field': 'order_count', 'direction': 'desc'},
        {'field': 'revenue', 'direction': 'desc'},
        {'field': 'order_month', 'direction': 'asc'},
    ]
    assert configured[3]['source']['arguments']['limit'] == 15
    assert configured[3]['source']['arguments']['sort'] == {'field': 'revenue', 'direction': 'desc'}
    assert 'initial_dashboard' not in json.loads(
        (ROOT / 'configs' / 'education.json').read_text(encoding='utf-8')
    )


def _nested_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _nested_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _nested_keys(item)


def test_olist_initial_dashboard_materializes_against_real_data():
    settings = json.loads((ROOT / 'configs' / 'olist.json').read_text(encoding='utf-8'))
    data_dir = (ROOT / settings['dataset']['data_dir']).resolve()
    if not data_dir.is_dir():
        pytest.skip('Olist CSV directory is not available')
    dataset = load_dataset(ROOT / settings['interface'], {'data_dir': str(data_dir)})
    trace = Trace()
    try:
        session = AnalysisSession(
            dataset,
            send,
            send,
            'revision_enabled',
            trace,
            initial_dashboard=settings['initial_dashboard'],
        )
        snapshot = session.dashboard.snapshot()
        assert snapshot['dashboard_revision'] == 1
        assert [view['title'] for view in snapshot['views']] == [
            'Monthly Orders Trend',
            'Average Review Score by State',
            'Orders by State',
            'Category Revenue (Top 15)',
            'Monthly Average Delivery Days',
        ]
        assert all(view['data'] for view in snapshot['views'])
        assert [view['columns'][view['y_field']]['unit'] for view in snapshot['views']] == [
            'orders', 'points', 'orders', 'BRL', 'days',
        ]
        for view in snapshot['views']:
            assert view['x_field'] in view['columns']
            assert view['y_field'] in view['columns']
            assert all(view['x_field'] in row and view['y_field'] in row for row in view['data'])

        monthly_orders, review_by_state, orders_by_state, category_revenue, monthly_delivery = snapshot['views']
        assert [row['order_month'] for row in monthly_orders['data']] == sorted(
            row['order_month'] for row in monthly_orders['data']
        )
        assert [row['order_month'] for row in monthly_delivery['data']] == sorted(
            row['order_month'] for row in monthly_delivery['data']
        )
        assert [row['order_count'] for row in orders_by_state['data']] == sorted(
            (row['order_count'] for row in orders_by_state['data']), reverse=True
        )
        assert [row['avg_review_score'] for row in review_by_state['data']] == sorted(
            (row['avg_review_score'] for row in review_by_state['data']), reverse=True
        )
        assert len(category_revenue['data']) == 15
        assert [row['revenue'] for row in category_revenue['data']] == sorted(
            (row['revenue'] for row in category_revenue['data']), reverse=True
        )
        assert category_revenue['truncated'] is True
    finally:
        trace.close()
        dataset.close()
