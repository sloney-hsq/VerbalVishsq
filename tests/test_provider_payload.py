"""Provider byte budgets must not weaken local validation or alter evidence."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest

from test_olist_adapter import olist_csvs  # noqa: F401
from refactor_next.backend.analytics import load_dataset
from refactor_next.backend.prompts import build_instructions
from refactor_next.backend.realtime import AnalysisSession
from refactor_next.backend.trace import Trace


@pytest.fixture
def session(olist_csvs):
    dataset = load_dataset(Path(__file__).resolve().parents[1] / 'datasets/olist/interface.py',
                           {'data_dir': str(olist_csvs)})
    events = []
    async def capture(event):
        events.append(deepcopy(event))
    instance = AnalysisSession(dataset, capture, capture, 'revision_enabled', Trace())
    yield instance, events
    asyncio.run(instance.close())
    dataset.close()


def test_real_olist_configuration_fits_with_headroom_and_keeps_every_tool(session):
    instance, events = session
    before = instance.toolbox.schemas()
    asyncio.run(instance.configure())
    event = next(e for e in events if e['type'] == 'session.update')
    encoded = json.dumps(event, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    assert len(encoded) < 192 * 1024
    assert {t['function']['name'] for t in event['session']['tools']} == {d['name'] for d in before}
    assert instance.toolbox.schemas() == before
    # Model-side compaction must not allow arbitrary/invalid query arguments locally.
    draft = instance.dashboard.begin_draft()
    result = instance.toolbox.execute('create_chart', {
        'source': {'tool': 'aggregate', 'arguments': {'metrics': ['invented_metric']}},
        'visual': {'type': 'bar', 'encoding': {'x': 'customer_state', 'y': 'order_count'}},
    }, draft)
    assert not result['success']
    assert not draft.document['views']
    instance.dashboard.discard(draft)


def test_prompt_does_not_repeat_parameter_schemas():
    definition = {'name': 'query', 'description': 'Query facts.',
                  'parameters': {'type': 'object', 'properties': {'marker': {'const': 'SCHEMA_ONLY_MARKER'}}}}
    prompt = build_instructions({'dataset_id': 'fixture'}, [definition])
    assert 'query' in prompt
    assert 'SCHEMA_ONLY_MARKER' not in prompt


def test_prompt_dashboard_summary_is_bounded_and_declares_rows_omitted():
    snapshot = {'dashboard_revision': 12, 'filters': [], 'views': [{
        'id': 'view-1', 'title': 'Evidence', 'source': {'tool': 'query', 'arguments': {}},
        'view_revision': 3, 'data': [{'x': i, 'text': 'ROW_PAYLOAD_MARKER'} for i in range(10000)],
        'columns': {'x': {'type': 'quantitative'}}, 'warnings': ['sampled'],
    }]}
    before = deepcopy(snapshot)
    text = build_instructions({'dataset_id': 'fixture'}, [], snapshot)
    assert len(text.encode()) < 16000
    state = json.loads(text.split('COMMITTED DASHBOARD:\n')[1])
    view = state['views'][0]
    assert view['id'] == 'view-1' and view['view_revision'] == 3
    assert view['warnings'] == ['sampled'] and view['source']['tool'] == 'query'
    assert view['data_summary']['returned_rows'] == 10000
    assert view['data_summary']['rows_included'] is False
    assert snapshot == before


def test_oversize_utf8_event_is_rejected_before_provider_send(session):
    instance, events = session
    async def run():
        with pytest.raises(ValueError, match='provider_message_too_large'):
            await instance.send({'type': 'session.update', 'session': {'instructions': '语' * 90000}})
    asyncio.run(run())
    assert not events


def test_large_tool_output_reports_delivery_limit_without_losing_committed_chart():
    from test_session import make
    async def run():
        instance, tools, browser, sent = make()
        execute = tools.execute
        def large_result(name, args, draft):
            result = execute(name, args, draft)
            result['payload']['large_table'] = 'x' * 300000
            return result
        tools.execute = large_result
        response = instance.protocol.begin_response(0)
        await instance.run_batch(response.id, [{'name': 'chart', 'call_id': 'c1', 'arguments': '{}'}])
        outputs = [json.loads(e['item']['output']) for e in sent
                   if e['type'] == 'conversation.item.create' and e['item']['type'] == 'function_call_output']
        assert len(outputs) == 1
        assert outputs[0]['error']['code'] == 'provider_result_too_large'
        assert outputs[0]['committed'] is True and outputs[0]['dashboard_revision'] == 1
        assert outputs[0]['payload'] is None
        assert instance.dashboard.snapshot()['views'] == [{'id': 'chart'}]
        assert next(e for e in browser if e['type'] == 'tool_result')['payload']['large_table'] == 'x' * 300000
        assert not instance.failed.is_set()
        await instance.close()
    asyncio.run(run())


def test_compact_metadata_deduplicates_only_identical_index_entries():
    from refactor_next.backend import provider_payload
    assert hasattr(provider_payload, 'dataset_context')
    description = {'dataset_id': 'example', 'metrics': [{'name': 'score', 'unit': 'points'}],
                   'metric_index': {'score': {'name': 'score', 'unit': 'points'}},
                   'field_index': {'score': {'name': 'score', 'grain': 'student'}}}
    before = deepcopy(description)
    context = provider_payload.dataset_context(description)
    assert context['metric_index'] == {'entries_from': 'metrics', 'key_field': 'name'}
    assert context['metrics'][0]['unit'] == 'points'
    assert context['field_index']['score']['grain'] == 'student'
    assert description == before


def test_oversize_followup_context_reports_budget_and_preserves_committed_state():
    from test_session import make
    async def run():
        instance, _, browser, sent = make()
        instance.dashboard.state['views'] = [{'id': 'large', 'metadata': {'notes': 'x' * 300000}}]
        instance.dashboard.state['dashboard_revision'] = 9
        with pytest.raises(ValueError, match='provider_message_too_large'):
            await instance.accept_text('Inspect this chart')
        assert any(e['type'] == 'error' and 'provider_message_too_large' in e['message'] for e in browser)
        assert not any(e['type'] == 'response.create' for e in sent)
        assert instance.dashboard.snapshot()['dashboard_revision'] == 9
        assert instance._pending_ticket is None and instance.failed.is_set()
        await instance.close()
    asyncio.run(run())


def test_schema_projection_retains_extra_domain_constraints():
    from refactor_next.backend.provider_payload import model_tool_definitions
    parameters = {'type': 'object', 'properties': {'field': {'enum': ['a', 'b']}}}
    branch = {'type': 'object', 'properties': {'tool': {'const': 'query'}, 'arguments': parameters},
              'required': ['tool', 'arguments'], 'additionalProperties': False,
              'not': {'properties': {'arguments': {'properties': {'field': {'const': 'b'}}}}}}
    definitions = [{'name': 'query', 'parameters': parameters},
                   {'name': 'special', 'parameters': {'oneOf': [branch]}}]
    assert model_tool_definitions(definitions) == definitions


def test_wire_encoder_counts_multibyte_json_and_preserves_under_budget_payload():
    from refactor_next.backend.provider_payload import encode_provider_event
    event = {'type': 'test', 'data': '\u8bed' * 100, 'quoted': '"\\\n'}
    assert json.loads(encode_provider_event(event)) == event
    with pytest.raises(ValueError, match='provider_message_too_large'):
        encode_provider_event({'type': 'test', 'data': '\u8bed' * 90000})


def test_schema_projection_preserves_unrelated_boolean_schema_branches():
    from refactor_next.backend.provider_payload import model_tool_definitions
    definitions = [{'name': 'query', 'parameters': {'oneOf': [False, {
        'type': 'object', 'properties': {'tool': True}}]}}]
    assert model_tool_definitions(definitions) == definitions
