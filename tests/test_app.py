import json
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from refactor_next.backend.main import _safe_ack, create_app, read_config
from refactor_next.backend.trace import Trace


def config(tmp_path):
    interface = tmp_path / 'interface.py'
    interface.write_text('''class Data:
 def describe(self): return {"dataset_id":"fixture", "version":"1", "description":"Fixture"}
 def tool_definitions(self): return []
 def execute(self, name, arguments, scope=None): raise ValueError(name)
 def close(self): pass
def open_dataset(config): return Data()
''')
    return {'interface': str(interface), 'dataset': {}, 'trace_dir': str(tmp_path / 'traces')}


def test_relative_env_config_resolves_from_repository_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('VERBALVIS_CONFIG', 'configs/education.json')

    settings = read_config()

    assert settings['interface'] == 'datasets/education/interface.py'


def test_relative_explicit_config_resolves_from_repository_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    settings = read_config('configs/education.json')

    assert settings['interface'] == 'datasets/education/interface.py'


def test_absolute_env_config_path_is_preserved(tmp_path, monkeypatch):
    config_path = tmp_path / 'absolute-config.json'
    config_path.write_text(json.dumps({'interface': 'absolute-interface.py'}), encoding='utf-8')
    monkeypatch.chdir(tmp_path.parent)
    monkeypatch.setenv('VERBALVIS_CONFIG', str(config_path))

    settings = read_config()

    assert settings['interface'] == 'absolute-interface.py'


def test_health_dataset_and_missing_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv('DASHSCOPE_API_KEY', raising=False)
    with TestClient(create_app(config(tmp_path))) as client:
        assert client.get('/api/health').json()['status'] == 'ok'
        assert client.get('/api/dataset').json()['dataset_id'] == 'fixture'
        with client.websocket_connect('/ws') as ws:
            assert ws.receive_json()['type'] == 'configuration_error'


def test_missing_frontend_build_hint_uses_standalone_repository_path(tmp_path, monkeypatch):
    monkeypatch.setattr('refactor_next.backend.main.ROOT', tmp_path)
    with TestClient(create_app(config(tmp_path))) as client:
        message = client.get('/').json()['message']

    assert 'refactor_next/frontend' not in message
    assert 'in frontend' in message


def test_real_socket_boundary_with_transport_double(tmp_path, monkeypatch):
    import asyncio
    class Provider:
        def __init__(self): self.queue = asyncio.Queue()
        async def send(self, message):
            event = json.loads(message)
            if event['type'] == 'session.update' and 'turn_detection' in event['session']:
                await self.queue.put(json.dumps({'type': 'session.updated', 'session': event['session']}))
        def __aiter__(self): return self
        async def __anext__(self): return await self.queue.get()
    @asynccontextmanager
    async def connect():
        yield Provider()
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'test-only-not-real')
    with TestClient(create_app(config(tmp_path), provider_factory=connect)) as client:
        with client.websocket_connect('/ws?condition=half_duplex') as ws:
            events = [ws.receive_json() for _ in range(4)]
            types = [event['type'] for event in events]
            assert types == ['input_policy', 'init', 'session_ready', 'input_policy']
            assert [event['condition'] for event in events if event['type'] == 'input_policy'] == ['turn_taking', 'turn_taking']
            with client.websocket_connect('/ws') as second:
                assert second.receive_json()['type'] == 'configuration_error'
        with client.websocket_connect('/ws?condition=wrong') as ws:
            assert ws.receive_json()['type'] == 'configuration_error'
    records = [json.loads(line) for path in (tmp_path / 'traces').glob('*.jsonl')
               for line in path.read_text(encoding='utf-8').splitlines()]
    assert records and all(record['condition'] in {'turn_taking', 'revision_enabled'} for record in records)


def test_websocket_freezes_query_context_and_records_session_started(tmp_path, monkeypatch):
    import asyncio
    class Provider:
        def __init__(self): self.queue = asyncio.Queue()
        async def send(self, message):
            event = json.loads(message)
            if event['type'] == 'session.update' and 'turn_detection' in event['session']:
                await self.queue.put(json.dumps({'type': 'session.updated', 'session': event['session']}))
        def __aiter__(self): return self
        async def __anext__(self): return await self.queue.get()
    @asynccontextmanager
    async def connect():
        yield Provider()
    settings = config(tmp_path)
    settings.update({'participant_id': 'config-p', 'trial_id': 'config-trial',
                     'task_id': 'config-task', 'trace_consent': False})
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'test-only-not-real')
    with TestClient(create_app(settings, provider_factory=connect)) as client:
        with client.websocket_connect('/ws?condition=half_duplex&participant_id=query-p&trial_id=query-trial') as ws:
            [ws.receive_json() for _ in range(4)]
    records = [json.loads(line) for path in (tmp_path / 'traces').glob('*.jsonl')
               for line in path.read_text(encoding='utf-8').splitlines()]
    started = next(row for row in records if row['event'] == 'session.started')
    assert started['condition'] == 'turn_taking'
    assert started['participant_id'] == 'query-p'
    assert started['trial_id'] == 'query-trial'
    assert started['task_id'] == 'config-task'
    assert started['dataset_id'] == 'fixture'
    assert started['data']['context_complete'] is True


@pytest.mark.parametrize('value', ['false', 0, 1, None])
def test_invalid_trace_consent_is_configuration_error_before_busy_claim(tmp_path, monkeypatch, value):
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'test-only-not-real')
    settings = config(tmp_path)
    settings['trace_consent'] = value
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect('/ws') as ws:
            assert ws.receive_json()['type'] == 'configuration_error'
        assert client.get('/api/health').json()['session_active'] is False


def test_invalid_experiment_token_and_dataset_assertion_are_configuration_errors(tmp_path, monkeypatch):
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'test-only-not-real')
    settings = config(tmp_path)
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect('/ws?participant_id=bad%20token') as ws:
            assert ws.receive_json()['type'] == 'configuration_error'
        with client.websocket_connect('/ws?dataset_id=other') as ws:
            assert ws.receive_json()['type'] == 'configuration_error'
        assert client.get('/api/health').json()['session_active'] is False


def test_safe_ack_whitelist_discards_payload_and_derives_request_mapping():
    class Session:
        _response_requests = {'response-1': 'server-request-1'}
    safe = _safe_ack({
        'type': 'playback_stopped', 'response_id': 'response-1', 'reason': 'natural_end',
        'request_id': 'forged-request', 'participant_id': 'forged-participant',
        'audio': 'raw-audio', 'data': {'pcm': 'raw-pcm'}, 'delta': 'private',
        'transcript': 'private', 'arguments': {'key': 'private'}, 'payload': {'x': 1},
        'playback_cursor': {'item_id': 'item-1', 'content_index': 2, 'audio_end_ms': 10,
                            'other': 'discard', 'duration_ms': float('nan')},
    }, Session())
    assert safe == {
        'type': 'playback_stopped', 'response_id': 'response-1', 'reason': 'natural_end',
        'playback_cursor': {'item_id': 'item-1', 'content_index': 2, 'audio_end_ms': 10},
        'request_id': 'server-request-1',
    }
    assert _safe_ack({'type': 'unknown', 'audio': 'x'}, Session()) is None
    assert _safe_ack({'type': 'playback_stopped', 'response_id': 'response-1', 'reason': 'anything'}, Session()) is None


def test_ack_huge_numeric_fields_are_rejected_and_client_seq_stays_in_data(tmp_path):
    class Session:
        _response_requests = {'response-1': 'server-request-1'}
    huge = 10 ** 400
    projection = _safe_ack({
        'type': 'dashboard_projection_ack', 'response_id': 'response-1', 'batch_id': 'batch-1',
        'revision': 3, 'seq': 42, 'client_monotonic_latency_ms': huge,
    }, Session())
    assert projection['client_seq'] == 42
    assert 'seq' not in projection and 'latency_ms' not in projection
    playback = _safe_ack({
        'type': 'playback_stopped', 'response_id': 'response-1', 'reason': 'interrupted',
        'playback_cursor': {'audio_end_ms': huge},
    }, Session())
    assert 'playback_cursor' not in playback
    path = tmp_path / 'trace.jsonl'
    trace = Trace(path)
    record = trace.record('browser.ack', **projection)
    trace.close()
    assert record['seq'] == 2
    assert record['data']['client_seq'] == 42
    assert 'seq' not in record['data']


def test_websocket_survives_huge_ack_numeric_fields(tmp_path, monkeypatch):
    import asyncio
    class Provider:
        def __init__(self): self.queue = asyncio.Queue()
        async def send(self, message):
            event = json.loads(message)
            if event['type'] == 'session.update' and 'turn_detection' in event['session']:
                await self.queue.put(json.dumps({'type': 'session.updated', 'session': event['session']}))
        def __aiter__(self): return self
        async def __anext__(self): return await self.queue.get()
    @asynccontextmanager
    async def connect():
        yield Provider()
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'test-only-not-real')
    with TestClient(create_app(config(tmp_path), provider_factory=connect)) as client:
        with client.websocket_connect('/ws') as ws:
            [ws.receive_json() for _ in range(4)]
            huge = 10 ** 400
            ws.send_json({'type': 'dashboard_projection_ack', 'response_id': 'response-1',
                          'batch_id': 'batch-1', 'revision': 3, 'seq': 17,
                          'client_monotonic_latency_ms': huge})
            ws.send_json({'type': 'playback_stopped', 'response_id': 'response-1', 'reason': 'interrupted',
                          'playback_cursor': {'audio_end_ms': huge}})
            ws.send_json({'type': 'text', 'text': 'continue after acknowledgement'})
            assert ws.receive_json()['type'] == 'transcript'
            assert client.get('/api/health').json()['session_active'] is True
    records = [json.loads(line) for path in (tmp_path / 'traces').glob('*.jsonl')
               for line in path.read_text(encoding='utf-8').splitlines()]
    projection = next(row for row in records if row['event'] == 'browser.ack')
    assert projection['data']['client_seq'] == 17
    assert 'seq' not in projection['data']


def test_websocket_materializes_configured_initial_dashboard(tmp_path, monkeypatch):
    interface = tmp_path / 'interface.py'
    interface.write_text('''class Data:
 def describe(self): return {"dataset_id":"fixture", "version":"1", "description":"Fixture"}
 def tool_definitions(self): return [{"name":"aggregate", "description":"Aggregate", "read_only":True, "parameters":{"type":"object", "properties":{}, "additionalProperties":False}}]
 def execute(self, name, arguments, scope=None): return {"success":True, "dataset_version":"1", "rows":[{"subject":"Math", "mean_score":75.0}], "columns":{"subject":{"type":"nominal"}, "mean_score":{"type":"quantitative"}}, "truncated":False}
 def close(self): pass
def open_dataset(config): return Data()
''')
    settings = {
        'interface': str(interface),
        'dataset': {},
        'trace_dir': str(tmp_path / 'traces'),
        'initial_dashboard': [{
            'source': {'tool': 'aggregate', 'arguments': {}},
            'chart_type': 'bar',
            'x': 'subject',
            'y': 'mean_score',
            'title': 'Configured chart',
        }],
    }

    import asyncio

    class Provider:
        def __init__(self):
            self.queue = asyncio.Queue()

        async def send(self, message):
            event = json.loads(message)
            if event['type'] == 'session.update' and 'turn_detection' in event['session']:
                await self.queue.put(json.dumps({'type': 'session.updated', 'session': event['session']}))

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.queue.get()

    @asynccontextmanager
    async def connect():
        yield Provider()

    monkeypatch.setenv('DASHSCOPE_API_KEY', 'test-only-not-real')
    with TestClient(create_app(settings, provider_factory=connect)) as client:
        with client.websocket_connect('/ws') as ws:
            events = [ws.receive_json() for _ in range(4)]

    init = next(event for event in events if event['type'] == 'init')
    assert init['dashboard_revision'] == 1
    assert [view['title'] for view in init['views']] == ['Configured chart']


def test_initial_dashboard_failure_is_reported_as_structured_configuration_error(tmp_path, monkeypatch):
    interface = tmp_path / 'interface.py'
    interface.write_text('''class Data:
 def describe(self): return {"dataset_id":"fixture", "version":"1", "description":"Fixture"}
 def tool_definitions(self): return [{"name":"aggregate", "description":"Aggregate", "read_only":True, "parameters":{"type":"object", "properties":{}, "additionalProperties":False}}]
 def execute(self, name, arguments, scope=None): return {"success":False, "dataset_version":"1", "error":{"code":"query_rejected", "message":"fixture query failed", "detail":{"retryable":False}}}
 def close(self): pass
def open_dataset(config): return Data()
''')
    settings = {
        'interface': str(interface),
        'dataset': {},
        'trace_dir': str(tmp_path / 'traces'),
        'initial_dashboard': [{
            'source': {'tool': 'aggregate', 'arguments': {}},
            'chart_type': 'bar',
            'x': 'subject',
            'y': 'mean_score',
            'title': 'Broken chart',
        }],
    }

    class Provider:
        async def send(self, _message):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    @asynccontextmanager
    async def connect():
        yield Provider()

    monkeypatch.setenv('DASHSCOPE_API_KEY', 'test-only-not-real')
    with TestClient(create_app(settings, provider_factory=connect)) as client:
        with client.websocket_connect('/ws') as ws:
            event = ws.receive_json()
        assert client.get('/api/health').json()['session_active'] is False

    assert event == {
        'type': 'configuration_error',
        'code': 'initial_dashboard_error',
        'message': 'Initial dashboard view 1 failed: fixture query failed',
        'details': {
            'view_index': 1,
            'tool_error': {
                'code': 'tool_error',
                'message': 'fixture query failed',
            },
        },
    }


def test_invalid_initial_dashboard_shape_is_a_configuration_error(tmp_path, monkeypatch):
    settings = config(tmp_path)
    settings['initial_dashboard'] = {}

    class Provider:
        async def send(self, _message):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    @asynccontextmanager
    async def connect():
        yield Provider()

    monkeypatch.setenv('DASHSCOPE_API_KEY', 'test-only-not-real')
    with TestClient(create_app(settings, provider_factory=connect)) as client:
        with client.websocket_connect('/ws') as ws:
            event = ws.receive_json()

    assert event['type'] == 'configuration_error'
    assert event['code'] == 'initial_dashboard_error'
    assert event['details']['view_index'] is None
    assert event['details']['tool_error']['code'] == 'invalid_initial_dashboard'
    assert 'must be a list' in event['message']


def test_trace_failure_releases_session_slot(tmp_path, monkeypatch):
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'test-only')
    def fail_trace(*args, **kwargs):
        raise OSError('Cannot open research trace')
    monkeypatch.setattr('refactor_next.backend.main.Trace', fail_trace)
    with TestClient(create_app(config(tmp_path))) as client:
        with client.websocket_connect('/ws') as ws:
            assert ws.receive_json()['type'] == 'error'
        assert client.get('/api/health').json()['session_active'] is False


def test_trace_write_failure_stops_formal_session_and_releases_slot(tmp_path, monkeypatch):
    import asyncio
    from refactor_next.backend.trace import Trace
    original_record = Trace.record
    def fail_after_start(self, event, **data):
        row = original_record(self, event, **data)
        if event == 'session.started':
            self.failed = True
        return row
    monkeypatch.setattr(Trace, 'record', fail_after_start)
    class Provider:
        def __init__(self): self.queue = asyncio.Queue()
        async def send(self, message):
            event = json.loads(message)
            if event['type'] == 'session.update' and 'turn_detection' in event['session']:
                await self.queue.put(json.dumps({'type': 'session.updated', 'session': event['session']}))
        def __aiter__(self): return self
        async def __anext__(self): return await self.queue.get()
    @asynccontextmanager
    async def connect():
        yield Provider()
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'test-only-not-real')
    with TestClient(create_app(config(tmp_path), provider_factory=connect)) as client:
        with client.websocket_connect('/ws') as ws:
            for _ in range(6):
                event = ws.receive_json()
                if event['type'] == 'error':
                    break
            assert event['type'] == 'error'
        assert client.get('/api/health').json()['session_active'] is False


def test_trace_close_exception_still_releases_busy_slot(tmp_path, monkeypatch):
    import asyncio
    from refactor_next.backend.trace import Trace
    original_close = Trace.close
    def close_then_raise(self):
        original_close(self)
        raise OSError('close failure')
    monkeypatch.setattr(Trace, 'close', close_then_raise)
    class Provider:
        def __init__(self): self.queue = asyncio.Queue()
        async def send(self, message):
            event = json.loads(message)
            if event['type'] == 'session.update' and 'turn_detection' in event['session']:
                await self.queue.put(json.dumps({'type': 'session.updated', 'session': event['session']}))
        def __aiter__(self): return self
        async def __anext__(self): return await self.queue.get()
    @asynccontextmanager
    async def connect():
        yield Provider()
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'test-only-not-real')
    with TestClient(create_app(config(tmp_path), provider_factory=connect)) as client:
        with client.websocket_connect('/ws') as ws:
            [ws.receive_json() for _ in range(4)]
        assert client.get('/api/health').json()['session_active'] is False
