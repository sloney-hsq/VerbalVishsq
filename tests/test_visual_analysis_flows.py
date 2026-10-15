"""Two complete analysis paths through public chart tools on a synthetic Olist snapshot."""
from scripts.check_visual_analysis import run_workflows
from test_olist_adapter import olist_csvs  # noqa: F401


def test_delivery_and_freight_workflows_commit_as_one_call_each(olist_csvs):
    steps, dashboard = run_workflows(olist_csvs)
    assert len(steps) >= 14
    assert all(step['success'] and step['revision'] >= 1 for step in steps)
    assert {'create_chart', 'update_chart', 'set_selection', 'fork_chart',
            'set_analysis_filters', 'undo_dashboard'} <= {step['tool'] for step in steps}
    assert dashboard['active_view_id'] in {view['id'] for view in dashboard['views']}
    assert dashboard['filters'] == []
