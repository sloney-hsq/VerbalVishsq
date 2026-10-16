import json
import re
from dataclasses import FrozenInstanceError

import pytest

from refactor_next.backend.trace import Trace
from refactor_next.backend.prompts import build_instructions


def test_trace_v2_freezes_context_and_separates_correlation(tmp_path):
    path = tmp_path / 'trace.jsonl'
    trace = Trace(path, condition='turn_taking', context={
        'participant_id': 'p-1', 'trial_id': 'trial.2', 'task_id': None,
        'dataset_id': 'fixture', 'condition': 'turn_taking',
    })
    session_id = trace.session_id
    with pytest.raises(AttributeError):
        trace.context = trace.context
    with pytest.raises(FrozenInstanceError):
        trace.context.participant_id = 'changed'
    trace.record('response.started', request_id='rq-1', response_id='rs-1',
                 participant_id='forged', dataset_id='other', session_id='forged-session', custom='ok')
    trace.record('assistant.playback_started', response_id='rs-1')
    trace.record('untrusted', response_id='Authorization: secret', reason='provider leaked transcript')
    trace.close()

    records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    assert [row['schema_version'] for row in records] == [2, 2, 2, 2]
    assert [row['seq'] for row in records] == [1, 2, 3, 4]
    assert all(row['session_id'] == session_id for row in records)
    assert all(row['participant_id'] == 'p-1' and row['dataset_id'] == 'fixture' for row in records)
    assert all(row['condition'] == 'turn_taking' for row in records)
    assert all(row['monotonic_ns'] > 0 and re.match(r'^\d{4}-\d\d-\d\dT', row['observed_at']) for row in records)
    assert records[1]['correlation']['request_id'] == 'rq-1'
    assert records[1]['correlation']['response_id'] == 'rs-1'
    assert all(key not in records[1]['data'] for key in
               ('request_id', 'response_id', 'participant_id', 'dataset_id', 'session_id'))
    assert records[1]['data']['custom'] == 'ok'
    assert records[3]['correlation']['response_id'] is None
    assert records[3]['data']['reason'] == '[redacted]'


def test_trace_rejects_noncanonical_context_and_non_boolean_consent(tmp_path):
    with pytest.raises(ValueError):
        Trace(tmp_path / 'bad.jsonl', context={'condition': 'half_duplex'})
    with pytest.raises(ValueError):
        Trace(tmp_path / 'bad-consent.jsonl', consent='false')


@pytest.mark.parametrize('consent', [False, True])
def test_trace_never_persists_audio_or_credentials_and_sanitizes_nested_json(consent, tmp_path):
    path = tmp_path / 'trace.jsonl'
    trace = Trace(path, consent=consent)
    trace.record('tool.execution_started', arguments=json.dumps({
        'audio': 'UklGR', 'authorization': 'Bearer secret', 'api_key': 'secret',
        'nested': {'transcript': 'private' if not consent else 'permitted'},
    }), audio=b'pcm', pcm='AAAA', credential='secret', transcript='private')
    trace.record('untrusted', value=float('nan'), detail={'token': float('inf')})
    trace.close()
    raw = path.read_text(encoding='utf-8')
    assert 'UklGR' not in raw and 'Bearer secret' not in raw and 'secret' not in raw
    assert 'AAAA' not in raw
    if not consent:
        assert 'private' not in raw
    assert 'NaN' not in raw and 'Infinity' not in raw
    rows = [json.loads(line) for line in raw.splitlines()]
    if consent:
        assert rows[1]['data']['arguments']['nested']['transcript'] == 'permitted'
    else:
        assert rows[1]['data']['arguments'] == '[redacted]'


def test_trace_limits_consent_transcript_to_named_fields_and_handles_write_failure(tmp_path):
    trace = Trace(tmp_path / 'trace.jsonl', consent=True)
    row = trace.record('provider.event', transcript='permitted', delta='not permitted', text='not permitted')
    assert row['data']['transcript'] == 'permitted'
    assert row['data']['delta'] == '[redacted]'
    assert row['data']['text'] == '[redacted]'
    class BrokenFile:
        def write(self, _value):
            raise OSError('closed')
        def flush(self):
            pass
        def close(self):
            raise OSError('closed')
    trace._file = BrokenFile()
    trace.record('provider.event', status='completed')
    assert trace.failed is True
    trace.close()


@pytest.mark.parametrize('consent', [False, True])
def test_argument_parser_is_bounded_and_complexity_failures_are_logged_without_raising(tmp_path, consent, monkeypatch):
    import refactor_next.backend.trace as trace_module
    path = tmp_path / 'trace.jsonl'
    trace = Trace(path, consent=consent)
    huge_integer = '1' * 5000
    long_string = '"' + ('x' * 5000) + '"'
    deeply_nested = '[' * 2500 + '0' + ']' * 2500
    for value in (huge_integer, long_string, deeply_nested):
        result = trace.record('tool.execution_started', arguments=value)
        if consent:
            detail = result['data']['arguments']
            assert detail['code'] in {'arguments_too_long', 'arguments_too_complex'}
            assert detail['length'] <= 4096
        else:
            assert result['data']['arguments'] == '[redacted]'

    original_loads = trace_module.json.loads
    def complex_loads(value):
        if value == '{}':
            raise RecursionError('deep parser failure')
        return original_loads(value)
    monkeypatch.setattr(trace_module.json, 'loads', complex_loads)
    result = trace.record('tool.execution_started', arguments='{}')
    if consent:
        assert result['data']['arguments'] == {'code': 'arguments_too_complex', 'length': 2}
    else:
        assert result['data']['arguments'] == '[redacted]'
    trace.close()
    assert len(path.read_text(encoding='utf-8').splitlines()) == 5


def test_consent_changes_trace_visibility_not_business_result():
    import copy
    import asyncio
    from refactor_next.backend.realtime import AnalysisSession

    class Dataset:
        description = {'dataset_id': 'test', 'dataset_version': 'v1'}
        definitions = []

    class Draft:
        def __init__(self, state):
            self.document = copy.deepcopy(state)
            self.base_revision = state['dashboard_revision']
            self.dirty = False

    class Store:
        def __init__(self):
            self.state = {'dashboard_revision': 0, 'views': [], 'filters': {}}
        def snapshot(self):
            return copy.deepcopy(self.state)
        def begin_draft(self):
            return Draft(self.state)
        def commit(self, draft):
            self.state = copy.deepcopy(draft.document)
            self.state['dashboard_revision'] += int(draft.dirty)
            return self.snapshot()
        def discard(self, _draft):
            pass

    class Toolbox:
        def __init__(self):
            self.calls = []
        def schemas(self):
            return []
        def effect_category(self, _name):
            return 'mutating'
        def execute(self, name, _args, draft):
            self.calls.append(name)
            draft.document['views'].append({'id': name})
            draft.dirty = True
            return {'success': True, 'payload': {'name': name}}

    async def run(consent):
        browser_events = []
        async def browser_send(event):
            browser_events.append(event)
        async def provider_send(event):
            pass
        dashboard, toolbox = Store(), Toolbox()
        session = AnalysisSession(Dataset(), browser_send, provider_send, 'revision_enabled',
                                  Trace(consent=consent), dashboard=dashboard, toolbox=toolbox)
        await session.accept_text('show a chart')
        await session.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await session.handle_provider_event({'type': 'response.done', 'response': {'id': 'p1', 'status': 'completed', 'output': [
            {'type': 'function_call', 'call_id': 'c1', 'name': 'chart', 'arguments': '{}'}]}})
        await asyncio.wait_for(asyncio.gather(*tuple(session._tasks)), 2)
        result = (dashboard.snapshot(), list(toolbox.calls), session.failed.is_set())
        await session.close()
        return result

    assert asyncio.run(run(False)) == asyncio.run(run(True))


def test_prompt_has_condition_neutral_revision_principles_without_taxonomy_output():
    text = build_instructions({'dataset_id': 'education', 'metrics': ['exam_score']}, [{'name': 'grade_summary'}])
    lowered = text.lower()
    for principle in (
        'Treat the latest accepted analytical request as authoritative.',
        'Adapt using the currently committed dashboard state.',
        'Preserve relevant committed visual context instead of unnecessarily restarting the workspace.',
        'Ignore superseded tool results and cancelled proposals as analytical evidence.',
        'Do not classify or announce revisions as Goal, Hypothesis, or Scope.',
    ):
        assert principle.lower() in lowered
    assert 'goal, hypothesis, or scope' not in lowered.split('do not classify or announce revisions as goal, hypothesis, or scope.')[0]
    assert 'output goal' not in lowered and 'order_count' not in lowered
    assert 'education' in text and 'grade_summary' in text


def test_prompt_does_not_accept_experiment_context_or_condition():
    text = build_instructions({'dataset_id': 'fixture', 'fields': ['neutral_field']}, [], {'dashboard_revision': 0})
    assert 'participant-secret' not in text and 'trial-secret' not in text
    assert 'turn_taking' not in text and 'revision_enabled' not in text


def test_prompt_requires_english_output_without_translating_user_records():
    text = build_instructions({'dataset_id': 'fixture'}, [])
    assert 'Use English for all spoken and written responses' in text
    assert 'even when the user speaks another language' in text
    assert "Preserve the user's verbatim transcript and raw dataset values" in text
    assert "Respond concisely in the user's language" not in text
