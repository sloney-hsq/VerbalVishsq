"""Consent-gated readable archives, exercised through the real session pipeline."""
import asyncio
import importlib
import importlib.util
import json

import pytest

from refactor_next.backend.trace import Trace
from test_session import Dataset, Store, Toolbox
from refactor_next.backend.realtime import AnalysisSession


def journal(root, consent=True):
    spec = importlib.util.find_spec('refactor_next.backend.conversation_log')
    assert spec is not None, 'Readable session archive is not implemented'
    cls = importlib.import_module('refactor_next.backend.conversation_log').SessionJournal
    return cls(root, session_id='session-test', consent=consent)


def rows(log, name='conversation.jsonl'):
    path = log.directory / name
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def user(text='Compare states', uid='u1', request='q1'):
    return {'type':'transcript','role':'user','text':text,'utterance_id':uid,
            'request_id':request,'completed':True}


def delta(text, response='r1', request='q1'):
    return {'type':'transcript','role':'assistant','delta':text,
            'response_id':response,'request_id':request}


def test_no_files_without_consent(tmp_path):
    log = journal(tmp_path / 'private', False)
    log.observe(user())
    log.observe(delta('Private words'))
    log.close()
    assert not (tmp_path / 'private').exists()


def test_reference_format_full_text_once_and_streamed_assistant_merge(tmp_path):
    log = journal(tmp_path)
    text = 'Long spoken analysis. ' * 350
    log.observe(user(text))
    log.observe(user(text))
    log.observe(delta('The evidence '))
    log.observe(delta('is mixed.'))
    log.finish_response('r1', 'completed')
    log.finish_response('r1', 'completed')
    result = rows(log)
    assert [r['role'] for r in result] == ['You','AI']
    assert result[0]['text'] == text
    assert result[1]['text'] == 'The evidence is mixed.'
    assert all({'ts','session_id','role','text','message_id','request_id'} <= set(r) for r in result)
    assert result[1]['response_id'] == 'r1'
    assert result[1]['status'] == 'completed'
    assert result[1]['delivery_scope'] == 'published_text_not_acoustic_playback'
    log.close()


def test_interrupt_and_disconnect_flush_only_real_published_text(tmp_path):
    log = journal(tmp_path)
    log.observe(delta('Partial answer'))
    log.finish_response('r1','interrupted')
    log.observe(delta('Next partial',response='r2'))
    log.observe({'type':'transcript','role':'user','text':'[Please repeat your request]','completed':True})
    log.close()
    log.close()
    assert [(r['text'],r['status']) for r in rows(log)] == [
        ('Partial answer','interrupted'),('Next partial','disconnected')]


def test_tools_link_user_request_and_keep_physical_success_separate_from_commit(tmp_path):
    log = journal(tmp_path)
    log.observe(user())
    log.record_tool({'name':'update_chart','call_id':'c1','arguments':json.dumps({
        'title':'Delivery comparison','api_key':'private-key',
        'nested':{'audio':'private-audio','authorization':'private-auth'}})},
        request_id='q1',response_id='r1',batch_id='b1',
        execution_status='succeeded',commit_status='superseded',
        result_success=True,elapsed_ms=12,dashboard_revision=3)
    record = rows(log,'tool_calls.jsonl')[0]
    assert record['user_message_id'] == rows(log)[0]['message_id']
    assert (record['request_id'],record['response_id'],record['batch_id'],record['call_id']) == ('q1','r1','b1','c1')
    assert record['result_success'] is True and record['commit_status'] == 'superseded'
    assert record['cancelled'] is True
    assert record['params']['title'] == 'Delivery comparison'
    assert record['metrics']['tool_duration_ms'] == 12
    raw = (log.directory / 'tool_calls.jsonl').read_text(encoding='utf-8')
    assert all(secret not in raw for secret in ('private-key','private-audio','private-auth'))
    log.close()


def make_session(tmp_path, *, browser_send=None, consent=True):
    log = journal(tmp_path,consent)
    emitted = []
    async def browser(event):
        if browser_send:
            await browser_send(event)
        emitted.append(event)
    async def provider(event):
        pass
    session = AnalysisSession(Dataset(),browser,provider,'revision_enabled',Trace(consent=consent),
                              dashboard=Store(),toolbox=Toolbox(),journal=log)
    return session,log,emitted


def test_session_records_only_permitted_delivery_and_links_real_tool_execution(tmp_path):
    async def scenario():
        s,log,_ = make_session(tmp_path)
        await s.accept_text('Create a chart')
        rid = s.protocol.current.id
        await s.handle_provider_event({'type':'response.created','response':{'id':'provider-1'}})
        await s.handle_provider_event({'type':'response.audio_transcript.delta','response_id':'provider-1','delta':'Creating it.'})
        await s.handle_provider_event({'type':'response.done','response':{'id':'provider-1','status':'completed','output':[
            {'type':'function_call','call_id':'c1','name':'chart','arguments':'{}'}]}})
        await asyncio.gather(*tuple(s._tasks))
        record = rows(log,'tool_calls.jsonl')[0]
        assert record['commit_status'] == 'committed'
        assert record['result_success'] is True
        assert record['response_id'] == rid
        assert record['request_id'] == rows(log)[0]['request_id']
        assert record['user_message_id'] == rows(log)[0]['message_id']
        assert record['assistant_message_id'] == rows(log)[1]['message_id']
        assert record['dashboard_revision'] == 1
        # A revoked generation cannot acquire an archive entry through late output.
        await s.accept_text('Stop')
        await s.handle_provider_event({'type':'response.audio_transcript.delta','response_id':'provider-1','delta':'STALE PRIVATE OUTPUT'})
        await s.close()
        assert 'STALE PRIVATE OUTPUT' not in (log.directory / 'conversation.jsonl').read_text(encoding='utf-8')
    asyncio.run(scenario())


def test_failed_browser_send_is_not_a_delivered_conversation_entry(tmp_path):
    async def scenario():
        async def fail(event):
            if event['type'] == 'transcript':
                raise OSError('browser disconnected')
        s,log,_ = make_session(tmp_path,browser_send=fail)
        with pytest.raises(OSError):
            await s.emit('transcript',role='user',text='Not delivered',utterance_id='u1',completed=True)
        await s.close()
        assert rows(log) == []
    asyncio.run(scenario())


def test_revision_archives_partial_once_before_new_user_message(tmp_path):
    async def scenario():
        s,log,_ = make_session(tmp_path)
        await s.accept_text('Old question')
        await s.handle_provider_event({'type':'response.created','response':{'id':'old-provider'}})
        await s.handle_provider_event({'type':'response.text.delta','response_id':'old-provider','delta':'Partial'})
        await s.accept_text('New question')
        await s.close()
        assert [(r['role'],r['text']) for r in rows(log)] == [
            ('You','Old question'),('AI','Partial'),('You','New question')]
        assert rows(log)[1]['status'] == 'interrupted'
    asyncio.run(scenario())


def test_stop_flushes_partial_and_duplicate_response_done_does_not_duplicate_text(tmp_path):
    async def scenario():
        s,log,_ = make_session(tmp_path)
        await s.accept_text('Question')
        await s.handle_provider_event({'type':'response.created','response':{'id':'p1'}})
        await s.handle_provider_event({'type':'response.text.delta','response_id':'p1','delta':'Partial'})
        await s.accept_text('Stop')
        done = {'type':'response.done','response':{'id':'p1','status':'cancelled','output':[]}}
        await s.handle_provider_event(done)
        await s.handle_provider_event(done)
        await s.close()
        assert [(r['text'],r['status']) for r in rows(log)] == [
            ('Question','completed'),('Partial','interrupted'),('Stop','completed')]
    asyncio.run(scenario())


def test_batch_rollback_logs_each_call_without_falsifying_individual_execution(tmp_path):
    async def scenario():
        s,log,_ = make_session(tmp_path)
        response = s.protocol.begin_response(0)
        await s.run_batch(response.id,[{'call_id':f'c{i}','name':name,'arguments':'{}'}
                                      for i,name in enumerate(['chart','fail','chart'])])
        result = rows(log,'tool_calls.jsonl')
        assert [r['execution_status'] for r in result] == ['succeeded','failed','skipped']
        assert [r['result_success'] for r in result] == [True,False,None]
        assert all(r['commit_status'] == 'failed' for r in result)
        assert s.dashboard.snapshot()['views'] == []
        await s.close()
    asyncio.run(scenario())


def test_archive_write_failure_is_reported_once_and_does_not_change_dashboard(tmp_path):
    async def scenario():
        s,log,emitted = make_session(tmp_path)
        log._files['conversation.jsonl'].close()
        await s.emit(**{'kind':'transcript','role':'user','text':'A','utterance_id':'u1'})
        await s.emit(**{'kind':'transcript','role':'user','text':'B','utterance_id':'u2'})
        await asyncio.gather(*tuple(s._tasks))
        assert log.failed
        assert len([e for e in emitted if e['type'] == 'error' and 'logging failed' in e['message']]) == 1
        assert s.dashboard.snapshot()['dashboard_revision'] == 0
        await s.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('enabled,consent,expected',[(True,True,True),(True,False,False),(False,True,False)])
def test_websocket_app_creates_archive_only_with_explicit_setting_and_consent(tmp_path,monkeypatch,enabled,consent,expected):
    from contextlib import asynccontextmanager
    from fastapi.testclient import TestClient
    from refactor_next.backend.main import create_app
    from test_app import config

    class Provider:
        def __init__(self):
            self.queue = asyncio.Queue()
        async def send(self,message):
            event = json.loads(message)
            if event['type'] == 'session.update' and 'turn_detection' in event['session']:
                await self.queue.put(json.dumps({'type':'session.updated','session':event['session']}))
            elif event['type'] == 'response.create':
                for response in [
                    {'type':'response.created','response':{'id':'p1'}},
                    {'type':'response.text.delta','response_id':'p1','delta':'Hello from the assistant.'},
                    {'type':'response.done','response':{'id':'p1','status':'completed','output':[]}},
                ]:
                    await self.queue.put(json.dumps(response))
        def __aiter__(self):
            return self
        async def __anext__(self):
            return await self.queue.get()
    @asynccontextmanager
    async def connect():
        yield Provider()
    settings = config(tmp_path)
    root = tmp_path / 'conversation_logs'
    settings.update(conversation_logging=enabled,conversation_log_dir=str(root),trace_consent=consent)
    monkeypatch.setenv('DASHSCOPE_API_KEY','test-only-not-real')
    with TestClient(create_app(settings,provider_factory=connect)) as client:
        with client.websocket_connect('/ws') as ws:
            [ws.receive_json() for _ in range(4)]
            ws.send_json({'type':'text','text':'Hello'})
            for _ in range(20):
                event = ws.receive_json()
                if event['type'] == 'input_policy' and event['phase'] == 'ready':
                    break
    paths = list(root.glob('*/conversation.jsonl'))
    assert bool(paths) is expected
    if expected:
        records = [json.loads(line) for line in paths[0].read_text(encoding='utf-8').splitlines()]
        assert [(r['role'],r['text']) for r in records] == [('You','Hello'),('AI','Hello from the assistant.')]
        trace_rows = [json.loads(line) for path in (tmp_path / 'traces').glob('*.jsonl')
                      for line in path.read_text(encoding='utf-8').splitlines()]
        assert records[0]['session_id'] == trace_rows[0]['session_id']
        assert records[0]['request_id'] == records[1]['request_id']


def test_invalid_logging_setting_is_rejected_at_startup(tmp_path):
    from fastapi.testclient import TestClient
    from refactor_next.backend.main import create_app
    from test_app import config
    settings = config(tmp_path)
    settings['conversation_logging'] = 'true'
    with pytest.raises(ValueError,match='conversation_logging'):
        with TestClient(create_app(settings)):
            pass


def test_superseded_physical_execution_is_archived_but_never_claimed_as_committed(tmp_path):
    async def scenario():
        s,log,_ = make_session(tmp_path)
        await s.accept_text('Old question')
        old = s.protocol.current.id
        s.toolbox.release.clear()
        task = asyncio.create_task(s.run_batch(old,[{'name':'chart','call_id':'c1','arguments':'{}'}]))
        assert await asyncio.to_thread(s.toolbox.started.wait,2)
        await s.accept_text('New question')
        s.toolbox.release.set()
        await task
        record = rows(log,'tool_calls.jsonl')[0]
        assert record['result_success'] is True
        assert record['execution_status'] == 'succeeded'
        assert record['commit_status'] == 'superseded' and record['cancelled']
        assert s.dashboard.snapshot()['dashboard_revision'] == 0
        await s.close()
    asyncio.run(scenario())


def test_tool_archive_reports_its_own_commit_revision_not_a_later_dashboard(tmp_path):
    async def scenario():
        s,log,_ = make_session(tmp_path)
        async def later_install(event):
            if event['type'] == 'conversation.item.create':
                s.dashboard.state['dashboard_revision'] = 17
        s.provider_send = later_install
        response = s.protocol.begin_response(0)
        await s.run_batch(response.id,[{'name':'chart','call_id':'c1','arguments':'{}'}])
        assert rows(log,'tool_calls.jsonl')[0]['dashboard_revision'] == 1
        await s.close()
    asyncio.run(scenario())


def test_log_destination_cannot_be_public_frontend_build(tmp_path):
    from fastapi.testclient import TestClient
    from refactor_next.backend.main import create_app, ROOT
    from test_app import config
    settings = config(tmp_path)
    settings.update(conversation_logging=True,conversation_log_dir=str(ROOT / 'frontend' / 'dist' / 'private'))
    with pytest.raises(ValueError,match='public frontend'):
        with TestClient(create_app(settings)):
            pass


def test_archive_initialization_failure_is_explicit_and_releases_session_slot(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from refactor_next.backend.main import create_app
    from test_app import config
    root = tmp_path / 'blocked'
    root.write_text('not a directory',encoding='utf-8')
    settings = config(tmp_path)
    settings.update(conversation_logging=True,conversation_log_dir=str(root),trace_consent=True)
    monkeypatch.setenv('DASHSCOPE_API_KEY','test-only-not-real')
    app = create_app(settings)
    with TestClient(app) as client:
        with client.websocket_connect('/ws') as ws:
            event = ws.receive_json()
        assert event['type'] == 'configuration_error'
        assert event['code'] == 'conversation_log_unavailable'
        assert str(root) not in event['message']
        assert app.state.busy is False


def test_readable_conversation_archives_are_ignored_by_git():
    from refactor_next.backend.main import ROOT
    assert 'conversation_logs/' in (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()
