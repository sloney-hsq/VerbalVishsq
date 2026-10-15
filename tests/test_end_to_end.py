import asyncio
import json
from pathlib import Path

from refactor_next.backend.analytics import load_dataset
from refactor_next.backend.realtime import AnalysisSession
from refactor_next.backend.trace import Trace


def test_real_education_interface_chart_filter_undo_through_session():
    async def scenario():
        root = Path(__file__).resolve().parents[1]
        dataset = load_dataset(root / 'datasets/education/interface.py', {})
        sent, browser = [], []
        async def provider_send(event): sent.append(event)
        async def browser_send(event): browser.append(event)
        session = AnalysisSession(dataset, browser_send, provider_send, 'revision_enabled', Trace())
        try:
            source = {'tool':'summarize_learning', 'arguments':{'group_by':'subject','measure':'mean_score'}}
            async def batch(name, args):
                session.protocol.revise()
                r = session.protocol.begin_response(session.dashboard.snapshot()['dashboard_revision'])
                await session.run_batch(r.id, [{'call_id':name, 'name':name, 'arguments':json.dumps(args)}])
            await batch('create_chart', {'source':source,'chart_type':'bar','x':'subject','y':'mean_score'})
            before = session.dashboard.snapshot()
            assert before['dashboard_revision'] == 1
            assert before['views'][0]['columns']['mean_score']['unit'] == 'points'
            await batch('set_analysis_filters', {'filters':[{'field':'cohort','op':'eq','value':'A'}]})
            assert session.dashboard.snapshot()['dashboard_revision'] == 2
            assert session.dashboard.snapshot()['filters'][0]['value'] == 'A'
            await batch('undo_dashboard', {})
            after = session.dashboard.snapshot()
            assert after['dashboard_revision'] == 3
            assert after['views'] == before['views'] and after['filters'] == []
            assert len([x for x in browser if x['type'] == 'dashboard_commit']) == 3
        finally:
            await session.close()
            dataset.close()
    asyncio.run(scenario())
