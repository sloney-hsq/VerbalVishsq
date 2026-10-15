import asyncio
import copy
import json
import threading

import pytest

from refactor_next.backend.realtime import AnalysisSession, ProviderContractError
from refactor_next.backend.trace import Trace


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
        assert draft.base_revision == self.state['dashboard_revision']
        self.state = copy.deepcopy(draft.document)
        self.state['dashboard_revision'] += int(draft.dirty)
        return self.snapshot()
    def discard(self, draft):
        pass


class Toolbox:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.calls = []
    def schemas(self):
        return []
    def effect_category(self, name):
        return 'read_only' if name == 'read' else 'mutating'
    def execute(self, name, args, draft):
        self.calls.append(name)
        self.started.set()
        assert self.release.wait(3)
        if name == 'fail':
            return {'success': False, 'error': 'bad request', 'payload': {}}
        if name in {'read', 'noop'}:
            return {'success': True, 'payload': {'name': name}}
        draft.document['views'].append({'id': name})
        draft.dirty = True
        return {'success': True, 'payload': {'name': name}}


def make(condition='revision_enabled', provider=None):
    browser, sent = [], []
    async def browser_send(event):
        browser.append(event)
    async def provider_send(event):
        sent.append(event)
        if provider:
            await provider(event)
    tools = Toolbox()
    session = AnalysisSession(Dataset(), browser_send, provider_send, condition, Trace(),
                              dashboard=Store(), toolbox=tools)
    return session, tools, browser, sent


def test_batch_failure_preserves_failing_call_error_and_marks_neighbors():
    async def scenario():
        session, tools, browser, _ = make()
        response = session.protocol.begin_response(0)
        calls = [{'call_id': str(index), 'name': name, 'arguments': '{}'}
                 for index, name in enumerate(('chart', 'fail', 'chart'))]
        await session.run_batch(response.id, calls)
        outcomes = [event for event in browser if event['type'] == 'tool_result']
        assert [item['error']['code'] for item in outcomes] == ['rolled_back', 'tool_error', 'skipped']
        assert outcomes[1]['error']['message'] == 'bad request'
        assert session.dashboard.snapshot()['views'] == []
        await session.close()
    asyncio.run(scenario())


def test_provider_configuration_is_negotiated_not_assumed():
    async def scenario():
        s, _, _, _ = make()
        with pytest.raises(ProviderContractError):
            await s.handle_provider_event({'type': 'session.updated', 'session': {}})
        await s.close()
    asyncio.run(scenario())


def test_late_created_binds_old_ticket_not_new_intent():
    async def scenario():
        s, _, browser, sent = make()
        await s.accept_text('old')
        old = s.protocol.current.id
        await s.accept_text('new')
        current = s.protocol.current.id
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'old-provider'}})
        assert s.provider_ids['old-provider'] == old != current
        assert not any(e['type'] == 'assistant_response_started' for e in browser)
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'old-provider', 'status': 'cancelled'}})
        assert len([e for e in sent if e['type'] == 'response.create']) == 2
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'new-provider'}})
        assert s.provider_ids['new-provider'] == current
        await s.close()
    asyncio.run(scenario())


def test_revision_during_physical_execution_discards_private_draft():
    async def scenario():
        s, tools, browser, sent = make()
        response = s.protocol.begin_response(0)
        tools.release.clear()
        job = asyncio.create_task(s.run_batch(response.id, [{'call_id': 'a', 'name': 'chart', 'arguments': '{}'}]))
        await asyncio.to_thread(tools.started.wait, 2)
        s.protocol.revise()
        tools.release.set()
        await job
        assert s.dashboard.snapshot()['dashboard_revision'] == 0
        assert not any(e['type'] == 'dashboard_commit' for e in browser)
        assert not any(e['type'] == 'conversation.item.create' for e in sent)
        await s.close()
    asyncio.run(scenario())


def test_batch_failure_rolls_back_and_undo_must_be_alone():
    async def scenario():
        s, _, browser, sent = make()
        r = s.protocol.begin_response(0)
        await s.run_batch(r.id, [{'call_id': 'a', 'name': 'chart', 'arguments': '{}'},
                               {'call_id': 'b', 'name': 'fail', 'arguments': '{}'}])
        assert s.dashboard.snapshot()['views'] == []
        outputs = [json.loads(e['item']['output']) for e in sent if e['type'] == 'conversation.item.create' and e['item']['type'] == 'function_call_output']
        assert len(outputs) == 2 and all(not o['success'] for o in outputs)
        await s.close()
    asyncio.run(scenario())


def test_partial_output_revocation_prevents_remaining_outputs_and_followup():
    async def scenario():
        s = None
        async def revoke_on_send(event):
            if event['type'] == 'conversation.item.create' and event['item']['type'] == 'function_call_output':
                s.protocol.revise()
        s, _, _, sent = make(provider=revoke_on_send)
        r = s.protocol.begin_response(0)
        await s.run_batch(r.id, [{'call_id': 'a', 'name': 'one', 'arguments': '{}'},
                               {'call_id': 'b', 'name': 'two', 'arguments': '{}'}])
        assert len([e for e in sent if e['type'] == 'conversation.item.create']) == 1
        assert not any(e['type'] == 'response.create' for e in sent)
        assert s.dashboard.snapshot()['dashboard_revision'] == 1
        await s.close()
    asyncio.run(scenario())


def test_duplex_input_gate():
    async def scenario():
        for condition, accepted in [('revision_enabled', True), ('turn_taking', False)]:
            s, _, _, sent = make(condition)
            await s.accept_text('first question')
            s._set_request_phase('tool_execution', response_id=s.current_request.response_id)
            sent.clear()
            assert await s.accept_audio('AA==') is accepted
            assert bool(sent) is accepted
            await s.close()
    asyncio.run(scenario())


def test_backchannel_holds_then_replays_audio_without_epoch_change():
    async def scenario():
        s, _, browser, _ = make()
        await s.accept_text('question')
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p'}})
        epoch = s.protocol.epoch
        await s.handle_provider_event({'type': 'input_audio_buffer.speech_started', 'item_id': 'u'})
        await s.handle_provider_event({'type': 'response.audio.delta', 'response_id': 'p', 'delta': 'AA=='})
        assert not any(e['type'] == 'audio' for e in browser)
        await s.accept_text('嗯', item_id='u')
        assert s.protocol.epoch == epoch
        assert len([e for e in browser if e['type'] == 'audio']) == 1
        await s.close()
    asyncio.run(scenario())


def test_turn_taking_waits_for_playback_ack_not_generation_end():
    async def scenario():
        s, _, _, _ = make('turn_taking')
        await s.accept_text('question')
        rid = s.protocol.current.id
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p'}})
        await s.handle_provider_event({'type': 'response.audio.delta', 'response_id': 'p', 'delta': 'AA=='})
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p', 'status': 'completed', 'output': []}})
        assert not await s.accept_audio('AA==')
        await s.playback_stopped('old', 'natural_end')
        assert not await s.accept_audio('AA==')
        await s.playback_stopped(rid, 'natural_end')
        assert await s.accept_audio('AA==')
        await s.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('transport', ['browser', 'provider'])
@pytest.mark.parametrize('resolution', ['backchannel', 'revision'])
def test_speech_during_first_result_publication_waits_for_resolution(transport, resolution):
    async def scenario():
        s, _, browser, sent = make()
        entered, release, exited = asyncio.Event(), asyncio.Event(), asyncio.Event()
        original = s.browser_send if transport == 'browser' else s.provider_send
        async def blocked_send(event):
            await original(event)
            if ((transport == 'browser' and event['type'] == 'tool_result') or
                (transport == 'provider' and event.get('item', {}).get('type') == 'function_call_output')) and event.get('call_id', event.get('item', {}).get('call_id')) == 'a':
                entered.set()
                await release.wait()
                exited.set()
        if transport == 'browser':
            s.browser_send = blocked_send
        else:
            s.provider_send = blocked_send
        response = s.protocol.begin_response(0)
        job = asyncio.create_task(s.run_batch(response.id, [
            {'call_id': 'a', 'name': 'one', 'arguments': '{}'},
            {'call_id': 'b', 'name': 'two', 'arguments': '{}'}]))
        await asyncio.wait_for(entered.wait(), 2)
        # Browser publication may hold its lock; suspension itself is synchronous.
        speech = asyncio.create_task(s.handle_provider_event({'type': 'input_audio_buffer.speech_started', 'item_id': 'u'}))
        await asyncio.sleep(0)
        assert s.protocol.current.authority == 'suspended'
        release.set()
        await speech
        await exited.wait()
        if resolution == 'backchannel':
            await s.accept_text('嗯', item_id='u')
        else:
            await s.accept_text('stop', item_id='u')
        await asyncio.wait_for(job, 2)
        outputs = [e['item']['call_id'] for e in sent if e.get('item', {}).get('type') == 'function_call_output']
        assert outputs == (['a', 'b'] if resolution == 'backchannel' else (['a'] if transport == 'provider' else []))
        assert len([e for e in sent if e['type'] == 'response.create']) == int(resolution == 'backchannel')
        assert s.dashboard.snapshot()['dashboard_revision'] == 1
        await s.close()
    asyncio.run(scenario())


def test_provider_output_failure_never_requests_followup():
    async def scenario():
        async def fail_output(event):
            if event.get('item', {}).get('type') == 'function_call_output':
                raise OSError('transport unavailable')
        s, _, browser, sent = make(provider=fail_output)
        response = s.protocol.begin_response(0)
        with pytest.raises(OSError, match='transport unavailable'):
            await s.run_batch(response.id, [{'call_id': 'a', 'name': 'one', 'arguments': '{}'}])
        assert not any(e['type'] == 'response.create' for e in sent)
        assert browser[-1]['type'] == 'tool_execution_finished'
        await s.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('stale_text', ['嗯', 'replace the chart'])
def test_stale_asr_final_cannot_resolve_newer_speech(stale_text):
    async def scenario():
        s, _, browser, sent = make()
        response = s.protocol.begin_response(0)
        for item_id in ['u1', 'u2']:
            await s.handle_provider_event({'type': 'input_audio_buffer.speech_started', 'item_id': item_id})
        await s.handle_provider_event({'type': 'conversation.item.input_audio_transcription.completed', 'item_id': 'u1', 'transcript': stale_text})
        assert s.protocol.current.id == response.id
        assert s.protocol.current.authority == 'suspended'
        assert not s._resolved.is_set()
        await s.handle_provider_event({'type': 'conversation.item.input_audio_transcription.completed', 'item_id': 'unknown', 'transcript': 'another question'})
        assert s.protocol.current.id == response.id and not s._resolved.is_set()
        await s.accept_text('嗯', item_id='u2')
        assert s.protocol.allowed(response.id)
        await s.accept_text('new question', item_id='u2')
        assert s.protocol.allowed(response.id) and not sent
        await s.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('kind', ['completed', 'failed'])
def test_unresolved_asr_revokes_blocked_tool_commit(kind):
    async def scenario():
        s, tools, browser, sent = make()
        response = s.protocol.begin_response(0)
        tools.release.clear()
        job = asyncio.create_task(s.run_batch(response.id, [{'call_id': 'a', 'name': 'chart', 'arguments': '{}'}]))
        assert await asyncio.to_thread(tools.started.wait, 2)
        await s.handle_provider_event({'type': 'input_audio_buffer.speech_started', 'item_id': 'u'})
        await s.handle_provider_event({'type': 'conversation.item.input_audio_transcription.' + kind, 'item_id': 'u', 'transcript': ''})
        tools.release.set()
        await asyncio.wait_for(job, 2)
        assert s.dashboard.snapshot()['dashboard_revision'] == 0
        assert not any(e['type'] == 'dashboard_commit' for e in browser)
        assert not any(e['type'] == 'response.create' for e in sent)
        assert any('repeat' in e.get('text', '').lower() for e in browser)
        assert s._resolved.is_set()
        await s.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('kind', ['response.audio.delta', 'response.text.delta'])
def test_browser_lock_rechecks_authority_before_publication(kind):
    async def scenario():
        s, _, browser, _ = make()
        response = s.protocol.begin_response(0)
        s.provider_ids['p'] = response.id
        await s._browser_lock.acquire()
        job = asyncio.create_task(s.handle_provider_event({'type': kind, 'response_id': 'p', 'delta': 'stale'}))
        await asyncio.sleep(0)
        s.protocol.revise()
        s._browser_lock.release()
        await asyncio.wait_for(job, 2)
        assert not any(e.get('response_id') == response.id for e in browser)
        await s.emit('assistant_playback_stop', response_id=response.id, reason='intent_revision')
        await s.emit('tool_execution_finished', response_id=response.id, batch_id='b')
        assert [e['type'] for e in browser] == ['assistant_playback_stop', 'tool_execution_finished']
        await s.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('transport', ['browser', 'provider'])
def test_send_lock_suspension_does_not_consume_delivery_permit(transport):
    async def scenario():
        s, _, browser, sent = make()
        response = s.protocol.begin_response(0)
        batch = s.protocol.admit(response.id, ['a'])
        s.protocol.finish_batch(batch.id, True)
        s.protocol.record_commit(batch.id, 0)
        lock = s._browser_lock if transport == 'browser' else s._provider_lock
        await lock.acquire()
        async def publish():
            if transport == 'browser':
                return await s.emit('tool_result', response_id=response.id, batch_id=batch.id, output_key='result:a', call_id='a')
            return await s.send({'type': 'conversation.item.create', 'item': {'type': 'function_call_output', 'call_id': 'a', 'output': '{}'}},
                                response_id=response.id, batch_id=batch.id, output_key='result:a')
        job = asyncio.create_task(publish())
        await asyncio.sleep(0)
        s.protocol.suspend()
        s._resolved.clear()
        lock.release()
        await asyncio.sleep(0)
        assert not browser and not sent and not job.done()
        s.protocol.resume()
        s._resolved.set()
        assert await asyncio.wait_for(job, 2)
        assert len(browser if transport == 'browser' else sent) == 1
        assert not await publish()
        await s.close()
    asyncio.run(scenario())


def test_asr_replay_tracking_is_bounded_and_evicted_unknown_finals_are_rejected():
    async def scenario():
        s, _, _, sent = make()
        response = s.protocol.begin_response(0)
        for index in range(270):
            item_id = 'u' + str(index)
            await s.handle_provider_event({'type': 'input_audio_buffer.speech_started', 'item_id': item_id})
            await s.accept_text('okay', item_id=item_id)
        assert len(s._utterances) <= 256
        await s.accept_text('new question', item_id='u0')
        assert s.protocol.allowed(response.id) and not sent
        await s.close()
    asyncio.run(scenario())


def test_lifecycle_trace_preserves_superseded_response_identity(tmp_path):
    async def scenario():
        s, _, _, _ = make()
        path = tmp_path / 'trace.jsonl'
        s.trace = Trace(path)
        await s.accept_text('old question')
        old = s.protocol.current
        await s.accept_text('new question')
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'old-provider'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'old-provider', 'status': 'cancelled'}})
        await s.close()
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        for name in ['response.started', 'intent.revoked', 'response.created', 'response.done']:
            record = next(e for e in records if e['event'] == name and e['correlation']['response_id'] == old.id)
            assert record['data']['intent_epoch'] == old.epoch
            assert record['data']['base_revision'] == 0
    asyncio.run(scenario())


def test_concurrent_accepted_input_cannot_reinstall_older_intent_after_send():
    async def scenario():
        s, _, _, sent = make()
        entered, release = asyncio.Event(), asyncio.Event()
        original = s.provider_send
        async def block_old_message(event):
            await original(event)
            if event.get('item', {}).get('content', [{}])[0].get('text') == 'old question':
                entered.set()
                await release.wait()
        s.provider_send = block_old_message
        old = asyncio.create_task(s.accept_text('old question'))
        await asyncio.wait_for(entered.wait(), 2)
        await s.handle_provider_event({'type': 'input_audio_buffer.speech_started', 'item_id': 'new-input'})
        newer = asyncio.create_task(s.accept_text('new question', item_id='new-input'))
        await asyncio.sleep(0)
        newest_id = s.protocol.current.id
        release.set()
        await asyncio.wait_for(asyncio.gather(old, newer), 2)
        assert s.protocol.current.id == newest_id
        assert s._pending_ticket == newest_id
        assert s._requested is None
        assert len([e for e in sent if e['type'] == 'response.create']) == 1
        await s.close()
    asyncio.run(scenario())


def test_request_chain_supersedes_once_and_settled_successor_is_not_revision(tmp_path):
    async def scenario():
        s, _, _, _ = make()
        path = tmp_path / 'trace.jsonl'
        s.trace = Trace(path)
        await s.accept_text('first question')
        first = s.current_request
        await s.accept_text('second question')
        second = s.current_request
        assert (first.request_id, second.parent_request_id, second.root_request_id,
                second.revision_index, second.phase) == (second.parent_request_id,
                first.request_id, first.request_id, 1, 'reasoning')
        assert s.requests[first.request_id].phase == 'superseded'
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'old-provider'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'old-provider', 'status': 'cancelled'}})
        assert s.current_request == second
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'new-provider'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'new-provider', 'status': 'completed', 'output': []}})
        assert s.current_request.phase == 'settled'
        await s.accept_text('third question')
        third = s.current_request
        assert (third.parent_request_id, third.revision_index) == (second.request_id, 2)
        await s.close()
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        by_event = lambda name: [r['data'] for r in records if r['event'] == name]
        assert len(by_event('user.request_received')) == 3
        assert len(by_event('revision.received')) == 1
        assert by_event('revision.received')[0]['previous_phase'] == 'reasoning'
        assert len(by_event('response.superseded')) == 1
        assert next(r for r in records if r['event'] == 'response.superseded')['correlation']['request_id'] == first.request_id
        assert len(by_event('request.received')) == 2
        assert all(r['correlation']['request_id'] is not None
                   for r in records if r['event'] == 'response.started')
    asyncio.run(scenario())


@pytest.mark.parametrize('phase', ['reasoning', 'tool_execution', 'committing', 'speaking'])
@pytest.mark.parametrize('source', ['typed', 'asr'])
def test_turn_taking_gate_uses_active_request_not_wire_phase(phase, source):
    async def scenario():
        s, _, _, sent = make('turn_taking')
        await s.accept_text('first question')
        first = s.current_request
        s._set_request_phase(phase, response_id=first.response_id)
        await s.input_policy('ready')  # stale compatibility phase cannot open the floor
        before = len([e for e in sent if e['type'] == 'response.create'])
        if source == 'asr':
            await s.handle_provider_event({'type': 'input_audio_buffer.speech_started', 'item_id': 'u2'})
            await s.accept_text('second question', item_id='u2')
        else:
            await s.accept_text('second question')
        assert s.current_request.request_id == first.request_id
        assert len([e for e in sent if e['type'] == 'response.create']) == before
        await s.close()
    asyncio.run(scenario())


def test_followup_is_same_request_and_never_ready_between_tool_rounds(tmp_path):
    async def scenario():
        s, _, browser, sent = make('turn_taking')
        path = tmp_path / 'trace.jsonl'
        s.trace = Trace(path)
        await s.accept_text('first question')
        first = s.current_request
        initial_response = first.response_id
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p1', 'status': 'completed', 'output': [
            {'type': 'function_call', 'call_id': 'c1', 'name': 'chart', 'arguments': '{}'}]}})
        assert s.current_request.phase == 'tool_execution'
        await asyncio.wait_for(asyncio.gather(*tuple(s._tasks)), 2)
        assert s.current_request.request_id == first.request_id
        assert s.current_request.response_id != initial_response
        assert s.current_request.phase == 'reasoning'
        assert not await s.accept_audio('AA==')
        assert not any(e['type'] == 'input_policy' and e['phase'] == 'ready' for e in browser)
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p2'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p2', 'status': 'completed', 'output': []}})
        assert s.current_request.phase == 'settled'
        assert await s.accept_audio('AA==')
        await s.close()
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        assert len([r for r in records if r['event'] == 'user.request_received']) == 1
        assert not any(r['event'] == 'response.superseded' for r in records)
        finished = [r for r in records if r['event'] == 'response.finished']
        assert len(finished) == 2
        assert len({r['correlation']['response_id'] for r in finished}) == 2
        assert all(r['correlation']['request_id'] == first.request_id for r in finished)
        assert len([r for r in records if r['event'] == 'request.settled']) == 1
        assert len([r for r in records if r['event'] == 'request.phase_changed' and
                    r['data']['to_phase'] == 'settled']) == 1
        execution_events = [r for r in records if r['event'].startswith('tool.execution_')]
        assert [r['event'] for r in execution_events] == ['tool.execution_started', 'tool.execution_finished']
        assert execution_events[0]['correlation']['call_id'] == 'c1'
        assert all(r['correlation']['request_id'] == first.request_id for r in execution_events)
        assert execution_events[1]['data']['status'] == 'succeeded'
        assert isinstance(execution_events[1]['data']['elapsed_ms'], int)
        commit_events = [r for r in records if r['event'] in {'dashboard.commit_started', 'dashboard.committed'}]
        assert [r['event'] for r in commit_events] == ['dashboard.commit_started', 'dashboard.committed']
        assert commit_events[-1]['data']['revision'] == 1
        browser_owner_events = [e for e in browser if e['type'] in {
            'assistant_response_started', 'transcript', 'audio', 'response_done',
            'tool_execution_started', 'tool_call', 'tool_result', 'dashboard_commit',
            'tool_execution_finished',
        } and e.get('response_id')]
        assert browser_owner_events
        assert all(e.get('request_id') == first.request_id for e in browser_owner_events)
    asyncio.run(scenario())


def test_physical_tool_trace_keeps_owner_request_when_tool_raises(tmp_path):
    async def scenario():
        s, tools, _, _ = make()
        path = tmp_path / 'trace.jsonl'
        s.trace = Trace(path)
        def raise_tool(_name, _arguments, _draft):
            raise RuntimeError('private tool failure')
        tools.execute = raise_tool
        await s.accept_text('request with failing physical tool')
        owner = s.current_request.request_id
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p1', 'status': 'completed', 'output': [
            {'type': 'function_call', 'call_id': 'c1', 'name': 'chart', 'arguments': '{}'}]}})
        await asyncio.wait_for(asyncio.gather(*tuple(s._tasks)), 2)
        await s.close()
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        events = [r for r in records if r['event'].startswith('tool.execution_')]
        assert [r['event'] for r in events] == ['tool.execution_started', 'tool.execution_finished']
        assert all(r['correlation']['request_id'] == owner for r in events)
        assert events[-1]['data']['status'] == 'raised'
    asyncio.run(scenario())


def test_skipped_tool_call_has_no_physical_execution_events(tmp_path):
    async def scenario():
        s, _, _, _ = make()
        path = tmp_path / 'trace.jsonl'
        s.trace = Trace(path)
        await s.accept_text('request with a failing batch')
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p1', 'status': 'completed', 'output': [
            {'type': 'function_call', 'call_id': 'c1', 'name': 'fail', 'arguments': '{}'},
            {'type': 'function_call', 'call_id': 'c2', 'name': 'chart', 'arguments': '{}'},
        ]}})
        await asyncio.wait_for(asyncio.gather(*tuple(s._tasks)), 2)
        await s.close()
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        events = [r for r in records if r['event'].startswith('tool.execution_')]
        assert [(r['event'], r['correlation']['call_id']) for r in events] == [
            ('tool.execution_started', 'c1'), ('tool.execution_finished', 'c1')]
    asyncio.run(scenario())


def test_audio_request_settles_only_on_matching_natural_ack_and_stale_done_cannot_settle_new(tmp_path):
    async def scenario():
        s, _, _, _ = make()
        path = tmp_path / 'trace-audio.jsonl'
        s.trace = Trace(path)
        await s.accept_text('first question')
        old_response = s.current_request.response_id
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.audio.delta', 'response_id': 'p1', 'delta': 'AA=='})
        assert s.current_request.phase == 'speaking'
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p1', 'status': 'completed', 'output': []}})
        assert s.current_request.phase == 'speaking'
        await s.playback_stopped(old_response, 'interrupted')
        assert s.current_request.phase == 'speaking'
        await s.accept_text('second question')
        current_id = s.current_request.request_id
        await s.playback_stopped(old_response, 'natural_end')
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p1', 'status': 'failed', 'output': []}})
        assert s.current_request.request_id == current_id
        assert s.current_request.phase == 'reasoning'
        await s.close()
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        starts = [r for r in records if r['event'] == 'assistant.playback_started']
        finishes = [r for r in records if r['event'] == 'assistant.playback_finished']
        assert len(starts) == 1
        assert starts[0]['data'] == {
            'intent_epoch': 1, 'base_revision': 0,
            'observation_source': 'server_audio_dispatch_proxy', 'actual_playback_observed': False,
        }
        assert finishes == []  # A late ACK for the superseded response is not playback completion.
    asyncio.run(scenario())


def test_valid_natural_end_ack_records_playback_finished_once(tmp_path):
    async def scenario():
        s, _, _, _ = make()
        path = tmp_path / 'trace.jsonl'
        s.trace = Trace(path)
        await s.accept_text('audio response')
        response_id = s.current_request.response_id
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.audio.delta', 'response_id': 'p1', 'delta': 'AA=='})
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p1', 'status': 'completed', 'output': []}})
        await s.playback_stopped(response_id, 'natural_end')
        await s.playback_stopped(response_id, 'natural_end')
        await s.close()
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        finished = [r for r in records if r['event'] == 'assistant.playback_finished']
        assert len(finished) == 1
        assert finished[0]['data']['observation_source'] == 'browser_natural_end_ack'
        assert finished[0]['correlation']['response_id'] == response_id
        assert len([r for r in records if r['event'] == 'request.settled']) == 1
    asyncio.run(scenario())


def test_stop_and_empty_terminate_without_new_request_or_superseded_event(tmp_path):
    async def scenario():
        s, _, _, _ = make()
        path = tmp_path / 'trace.jsonl'
        s.trace = Trace(path)
        await s.accept_text('first question')
        first_id = s.current_request.request_id
        await s.accept_text('stop')
        assert s.current_request.request_id == first_id
        assert (s.current_request.phase, s.current_request.terminal_reason) == ('settled', 'user_stop')
        await s.accept_text('')
        assert s.current_request.request_id == first_id
        await s.close()
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        assert not any(r['event'] == 'response.superseded' for r in records)
    asyncio.run(scenario())


def test_late_physical_tool_from_superseded_request_cannot_commit_or_publish_model_output(tmp_path):
    async def scenario():
        s, tools, browser, sent = make()
        path = tmp_path / 'trace.jsonl'
        s.trace = Trace(path)
        tools.release.clear()
        await s.accept_text('old request')
        old = s.current_request
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p-old'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p-old', 'status': 'completed', 'output': [
            {'type': 'function_call', 'call_id': 'c-old', 'name': 'chart', 'arguments': '{}'}]}})
        await asyncio.to_thread(tools.started.wait, 2)
        await s.accept_text('replacement request')
        current = s.current_request
        tools.release.set()
        await asyncio.wait_for(asyncio.gather(*tuple(s._tasks)), 2)
        assert s.requests[old.request_id].phase == 'superseded'
        assert s.current_request == current and current.phase == 'reasoning'
        assert s.dashboard.snapshot()['dashboard_revision'] == 0
        assert not any(e.get('item', {}).get('type') == 'function_call_output' for e in sent)
        assert not any(e['type'] == 'dashboard_commit' for e in browser)
        await s.close()
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        events = [r for r in records if r['event'].startswith('tool.execution_')]
        assert [r['event'] for r in events] == ['tool.execution_started', 'tool.execution_finished']
        assert all(r['correlation']['request_id'] == old.request_id for r in events)
        terminal = [event for event in browser if event['type'] == 'tool_execution_finished']
        assert len(terminal) == 1
        assert terminal[0]['status'] == 'superseded'
        assert terminal[0]['request_id'] == old.request_id
        assert terminal[0]['followup_requested'] is False
    asyncio.run(scenario())


def test_stale_input_policy_waiting_on_lock_cannot_publish_after_new_request():
    async def scenario():
        s, _, browser, _ = make()
        await s.accept_text('first request')
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p1', 'status': 'completed', 'output': []}})
        await s._browser_lock.acquire()
        old_policy = asyncio.create_task(s.input_policy('ready'))
        await asyncio.sleep(0)
        new_request = asyncio.create_task(s.accept_text('next request'))
        await asyncio.sleep(0)
        current_id = s.current_request.request_id
        s._browser_lock.release()
        await asyncio.wait_for(asyncio.gather(old_policy, new_request), 2)
        policies = [e for e in browser if e['type'] == 'input_policy']
        assert policies[-1]['phase'] == 'followup_generating'
        assert s.current_request.request_id == current_id
        await s.close()
    asyncio.run(scenario())


def test_natural_playback_ack_during_suspended_overlap_still_settles_owning_request():
    async def scenario():
        s, _, _, _ = make('turn_taking')
        await s.accept_text('first request')
        response_id = s.current_request.response_id
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.audio.delta', 'response_id': 'p1', 'delta': 'AA=='})
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p1', 'status': 'completed', 'output': []}})
        await s.handle_provider_event({'type': 'input_audio_buffer.speech_started', 'item_id': 'u2'})
        await s.playback_stopped(response_id, 'natural_end')
        await s.accept_text('嗯', item_id='u2')
        assert s.current_request.phase == 'settled'
        assert await s.accept_audio('AA==')
        await s.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('phase', ['reasoning', 'tool_execution', 'committing', 'speaking'])
def test_revision_enabled_records_exact_active_phase_before_superseding(phase, tmp_path):
    async def scenario():
        s, _, browser, _ = make('revision_enabled')
        path = tmp_path / (phase + '.jsonl')
        s.trace = Trace(path)
        await s.accept_text('first request')
        previous = s.current_request
        s._set_request_phase(phase, response_id=previous.response_id)
        await s.accept_text('replacement request')
        assert s.current_request.parent_request_id == previous.request_id
        assert s.requests[previous.request_id].phase == 'superseded'
        await s.close()
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        revision = next(row['data'] for row in records if row['event'] == 'revision.received')
        assert revision['previous_phase'] == phase
        assert revision['in_flight'] is True
        assert len([row for row in records if row['event'] == 'response.superseded']) == 1
        revision_messages = [event for event in browser if event['type'] == 'revision_received']
        superseded_messages = [event for event in browser if event['type'] == 'response_superseded']
        user_request = [event for event in browser if event['type'] == 'transcript' and event.get('text') == 'replacement request']
        assert len(user_request) == 1
        assert revision_messages == [{
            'type': 'revision_received', 'request_id': s.current_request.request_id,
            'previous_request_id': previous.request_id, 'previous_response_id': previous.response_id,
            'revision_index': 1, 'previous_phase': phase, 'utterance_id': user_request[0]['utterance_id'],
            'seq': revision_messages[0]['seq'],
        }]
        assert superseded_messages == [{
            'type': 'response_superseded', 'request_id': previous.request_id,
            'response_id': previous.response_id, 'superseding_request_id': s.current_request.request_id,
            'previous_phase': phase, 'seq': superseded_messages[0]['seq'],
        }]
        assert revision_messages[0]['seq'] < superseded_messages[0]['seq']
        assert user_request[0]['request_id'] == s.current_request.request_id
    asyncio.run(scenario())


def test_browser_revision_feedback_is_absent_for_settled_requests_and_control_input():
    async def scenario():
        s, _, browser, _ = make()
        await s.accept_text('first request')
        first = s.current_request
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p1', 'status': 'completed', 'output': []}})
        await s.accept_text('after settlement')
        await s.accept_text('嗯')
        await s.accept_text('stop')
        await s.accept_text('')
        assert not [event for event in browser if event['type'] in {'revision_received', 'response_superseded'}]
        transcript = [event for event in browser if event['type'] == 'transcript' and event.get('text') == 'after settlement']
        assert len(transcript) == 1 and transcript[0]['request_id'] != first.request_id
        assert all(event.get('seq', 0) > 0 for event in browser)
        assert [event['seq'] for event in browser] == sorted(set(event['seq'] for event in browser))
        await s.close()
    asyncio.run(scenario())


def test_turn_taking_rejection_emits_no_revision_feedback():
    async def scenario():
        s, _, browser, _ = make('turn_taking')
        await s.accept_text('accepted first')
        active = s.current_request
        await s.accept_text('rejected while busy')
        assert s.current_request == active
        assert not [event for event in browser if event['type'] in {'revision_received', 'response_superseded'}]
        assert not [event for event in browser if event['type'] == 'transcript' and event.get('text') == 'rejected while busy']
        await s.close()
    asyncio.run(scenario())


def test_followup_response_create_failure_fails_session_and_clears_ticket():
    async def scenario():
        creates = 0
        async def fail_followup_create(event):
            nonlocal creates
            if event.get('type') == 'response.create':
                creates += 1
                if creates == 2:
                    raise OSError('follow-up create failed')
        s, _, browser, _ = make(provider=fail_followup_create)
        await s.accept_text('request with a tool')
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p1', 'status': 'completed', 'output': [
            {'type': 'function_call', 'call_id': 'c1', 'name': 'chart', 'arguments': '{}'}]}})
        await asyncio.gather(*tuple(s._tasks), return_exceptions=True)
        await asyncio.sleep(0)
        await asyncio.gather(*tuple(s._tasks), return_exceptions=True)
        assert s.current_request.phase == 'failed'
        assert s.failed.is_set()
        assert s._pending_ticket is None
        assert any(event['type'] == 'error' for event in browser)
        await s.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('completion', ['text', 'natural_ack'])
def test_asr_timeout_after_settlement_cleans_overlap_without_rewriting_request(completion, monkeypatch):
    async def scenario():
        s, _, browser, sent = make('turn_taking')
        await s.accept_text('first request')
        response_id = s.current_request.response_id
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        if completion == 'text':
            await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p1', 'status': 'completed', 'output': []}})
        else:
            await s.handle_provider_event({'type': 'response.audio.delta', 'response_id': 'p1', 'delta': 'AA=='})
            await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p1', 'status': 'completed', 'output': []}})
            await s.playback_stopped(response_id, 'natural_end')
        settled = s.current_request
        entered, release = asyncio.Event(), asyncio.Event()
        async def fast_timeout(awaitable, timeout):
            awaitable.close()
            entered.set()
            await release.wait()
            raise TimeoutError()
        monkeypatch.setattr('refactor_next.backend.realtime.asyncio.wait_for', fast_timeout)
        await s.handle_provider_event({'type': 'input_audio_buffer.speech_started', 'item_id': 'u-timeout'})
        await entered.wait()
        await s.handle_provider_event({'type': 'response.text.delta', 'response_id': 'p1', 'delta': 'held'})
        release.set()
        await asyncio.gather(*tuple(s._tasks))
        assert s.current_request == settled
        assert s.current_request.phase == 'settled'
        assert s._overlap_id is None
        assert s._resolved.is_set()
        assert s._held_events == [] and s._held_bytes == 0
        assert any(event.get('text') == '[Please repeat your request]' for event in browser)
        assert any(event['type'] == 'input_policy' and event['phase'] == 'ready' for event in browser)
        assert 'u-timeout' in s._utterances
        assert len(s._utterances) <= 256
        response_creates = sum(event['type'] == 'response.create' for event in sent)
        await s.handle_provider_event({'type': 'input_audio_buffer.speech_started', 'item_id': 'u-timeout'})
        await s.handle_provider_event({'type': 'conversation.item.input_audio_transcription.completed',
                                       'item_id': 'u-timeout', 'transcript': 'replayed analytical request'})
        assert s.current_request == settled
        assert s.current_request.revision_index == 0
        assert sum(event['type'] == 'response.create' for event in sent) == response_creates
        await s.close()
    asyncio.run(scenario())


def test_duplicate_call_id_batch_admission_failure_terminates_current_request():
    async def scenario():
        s, _, browser, _ = make()
        await s.accept_text('request with invalid duplicate tools')
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p1', 'status': 'completed', 'output': [
            {'type': 'function_call', 'call_id': 'same', 'name': 'chart', 'arguments': '{}'},
            {'type': 'function_call', 'call_id': 'same', 'name': 'chart', 'arguments': '{}'}]}})
        await asyncio.wait_for(asyncio.gather(*tuple(s._tasks)), 2)
        assert s.current_request.phase == 'failed'
        assert s.failed.is_set()
        assert any(event['type'] == 'error' for event in browser)
        await s.close()
    asyncio.run(scenario())


def test_current_commit_revision_conflict_does_not_leave_request_in_flight(tmp_path):
    async def scenario():
        s, _, browser, _ = make()
        path = tmp_path / 'trace.jsonl'
        s.trace = Trace(path)
        await s.accept_text('request with commit conflict')
        s.dashboard.state['dashboard_revision'] = 1
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {'id': 'p1', 'status': 'completed', 'output': [
            {'type': 'function_call', 'call_id': 'c1', 'name': 'chart', 'arguments': '{}'}]}})
        await asyncio.wait_for(asyncio.gather(*tuple(s._tasks)), 2)
        assert s.current_request.phase == 'failed'
        assert not s.failed.is_set()
        assert s.phase == 'ready'
        assert not any(event['type'] == 'error' for event in browser)
        await s.close()
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        rejected = [r for r in records if r['event'] == 'dashboard.commit_rejected']
        assert len(rejected) == 1
        assert rejected[0]['data']['reason'] == 'stale_or_revision_conflict'
        assert not any(r['event'] == 'dashboard.committed' for r in records)
    asyncio.run(scenario())


@pytest.mark.parametrize('names,expected_commit,expected_revision', [
    (['read'], 'read_only', 0),
    (['noop'], 'no_change', 0),
    (['chart'], 'committed', 1),
    (['chart', 'second'], 'committed', 1),
    (['chart', 'fail'], 'failed', 0),
    (['chart', 'fail', 'skipped'], 'failed', 0),
])
def test_batch_outcome_matrix_and_publication(names, expected_commit, expected_revision, tmp_path):
    async def scenario():
        s, _, browser, sent = make()
        path = tmp_path / 'trace.jsonl'
        s.trace = Trace(path)
        response = s.protocol.begin_response(0)
        calls = [{'call_id': f'c{index}', 'name': name, 'arguments': '{}'}
                 for index, name in enumerate(names)]
        await s.run_batch(response.id, calls)
        expected_execution = 'failed' if expected_commit == 'failed' else 'succeeded'
        expected = {'execution_status': expected_execution,
                    'commit_status': expected_commit,
                    'state_changed': expected_commit == 'committed'}
        terminal = [e for e in browser if e['type'] == 'tool_execution_finished']
        assert len(terminal) == 1
        assert {key: terminal[0][key] for key in expected} == expected
        assert s.dashboard.snapshot()['dashboard_revision'] == expected_revision
        assert len([e for e in browser if e['type'] == 'dashboard_commit']) == int(expected_commit == 'committed')
        results = [e for e in browser if e['type'] == 'tool_result']
        outputs = [json.loads(e['item']['output']) for e in sent
                   if e.get('item', {}).get('type') == 'function_call_output']
        assert len(results) == len(outputs) == len(calls)
        assert all({key: item[key] for key in expected} == expected for item in results + outputs)
        if expected_commit == 'failed':
            assert all(item['success'] is False for item in results + outputs)
            expected_codes = ['rolled_back', 'tool_error', *(['skipped'] if len(calls) > 2 else [])]
            assert [item['error']['code'] for item in results] == expected_codes
            assert [item['error']['code'] for item in outputs] == expected_codes
        await s.close()
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        outcomes = [r for r in records if r['event'] == 'batch.outcome']
        assert len(outcomes) == 1
        assert outcomes[0]['correlation']['request_id'] is None
        assert outcomes[0]['data']['call_ids'] == [call['call_id'] for call in calls]
        assert {key: outcomes[0]['data'][key] for key in expected} == expected
    asyncio.run(scenario())


@pytest.mark.parametrize('physical_failure', [False, True])
def test_revision_after_physical_execution_preserves_execution_fact(physical_failure):
    async def scenario():
        s, tools, browser, sent = make()
        response = s.protocol.begin_response(0)
        tools.release.clear()
        name = 'fail' if physical_failure else 'chart'
        job = asyncio.create_task(s.run_batch(response.id, [
            {'call_id': 'a', 'name': name, 'arguments': '{}'}]))
        assert await asyncio.to_thread(tools.started.wait, 2)
        s.protocol.revise()
        tools.release.set()
        await asyncio.wait_for(job, 2)
        terminal = [e for e in browser if e['type'] == 'tool_execution_finished']
        assert len(terminal) == 1
        assert (terminal[0]['execution_status'], terminal[0]['commit_status'],
                terminal[0]['state_changed'], terminal[0]['followup_requested']) == (
                    'failed' if physical_failure else 'succeeded', 'superseded', False, False)
        assert not [e for e in browser if e['type'] in {'tool_call', 'tool_result', 'dashboard_commit'}]
        assert not [e for e in sent if e.get('item', {}).get('type') == 'function_call_output']
        await s.close()
    asyncio.run(scenario())


def test_conflict_reports_successful_execution_without_session_fatality(tmp_path):
    async def scenario():
        s, _, browser, sent = make()
        path = tmp_path / 'trace.jsonl'
        s.trace = Trace(path)
        await s.accept_text('conflicting request')
        s.dashboard.state['dashboard_revision'] = 1
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {
            'id': 'p1', 'status': 'completed', 'output': [
                {'type': 'function_call', 'call_id': 'c1', 'name': 'chart', 'arguments': '{}'}]}})
        await asyncio.wait_for(asyncio.gather(*tuple(s._tasks)), 2)
        terminal = [e for e in browser if e['type'] == 'tool_execution_finished']
        assert len(terminal) == 1
        assert (terminal[0]['execution_status'], terminal[0]['commit_status'],
                terminal[0]['state_changed'], terminal[0]['followup_requested']) == (
                    'succeeded', 'conflicted', False, False)
        assert s.current_request.phase == 'failed'
        assert not s.failed.is_set()
        assert s.phase == 'ready'
        assert not [e for e in browser if e['type'] in {'tool_call', 'tool_result', 'dashboard_commit', 'error'}]
        assert not [e for e in sent if e.get('item', {}).get('type') == 'function_call_output']
        await s.close()
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        outcomes = [r for r in records if r['event'] == 'batch.outcome']
        assert len(outcomes) == 1
        assert outcomes[0]['correlation']['request_id'] == s.current_request.request_id
        assert outcomes[0]['data']['call_ids'] == ['c1']
        assert outcomes[0]['data']['commit_status'] == 'conflicted'
    asyncio.run(scenario())


def test_dashboard_cas_race_after_protocol_precheck_is_conflicted():
    async def scenario():
        s, _, browser, sent = make()
        await s.accept_text('racing request')
        def racing_commit(draft):
            s.dashboard.state['dashboard_revision'] = 1
            raise ValueError('Dashboard revision conflict')
        s.dashboard.commit = racing_commit
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {
            'id': 'p1', 'status': 'completed', 'output': [
                {'type': 'function_call', 'call_id': 'c1', 'name': 'chart', 'arguments': '{}'}]}})
        await asyncio.gather(*tuple(s._tasks), return_exceptions=True)
        terminal = [e for e in browser if e['type'] == 'tool_execution_finished']
        assert len(terminal) == 1
        assert terminal[0]['execution_status'] == 'succeeded'
        assert terminal[0]['commit_status'] == 'conflicted'
        assert terminal[0]['state_changed'] is False
        assert s.current_request.phase == 'failed'
        assert not s.failed.is_set() and s.phase == 'ready'
        assert not [e for e in browser if e['type'] in {'dashboard_commit', 'tool_call', 'tool_result'}]
        assert not [e for e in sent if e.get('item', {}).get('type') == 'function_call_output']
        await s.close()
    asyncio.run(scenario())


def test_followup_dispatch_failure_keeps_terminal_outcome_but_not_followup():
    async def scenario():
        creates = 0
        async def provider(event):
            nonlocal creates
            if event['type'] == 'response.create':
                creates += 1
                if creates == 2:
                    raise OSError('follow-up unavailable')
        s, _, browser, _ = make(provider=provider)
        await s.accept_text('question')
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {
            'id': 'p1', 'status': 'completed', 'output': [
                {'type': 'function_call', 'call_id': 'c1', 'name': 'read', 'arguments': '{}'}]}})
        await asyncio.gather(*tuple(s._tasks), return_exceptions=True)
        await asyncio.sleep(0)
        await asyncio.gather(*tuple(s._tasks), return_exceptions=True)
        terminal = [e for e in browser if e['type'] == 'tool_execution_finished']
        assert len(terminal) == 1
        assert terminal[0]['commit_status'] == 'read_only'
        assert terminal[0]['followup_requested'] is False
        assert s.current_request.phase == 'failed'
        await s.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('name,commit_status', [
    ('read', 'read_only'), ('noop', 'no_change'), ('fail', 'failed')])
def test_active_noncommitting_batch_dispatches_bound_followup(name, commit_status):
    async def scenario():
        s, _, browser, sent = make('turn_taking')
        await s.accept_text('question')
        request_id = s.current_request.request_id
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {
            'id': 'p1', 'status': 'completed', 'output': [
                {'type': 'function_call', 'call_id': 'c1', 'name': name, 'arguments': '{}'}]}})
        await asyncio.wait_for(asyncio.gather(*tuple(s._tasks)), 2)
        terminal = [e for e in browser if e['type'] == 'tool_execution_finished']
        assert len(terminal) == 1
        assert terminal[0]['commit_status'] == commit_status
        assert terminal[0]['followup_requested'] is True
        assert len([e for e in sent if e['type'] == 'response.create']) == 2
        assert s.current_request.request_id == request_id
        assert s.current_request.phase == 'reasoning'
        assert s.current_request.response_id != terminal[0]['response_id']
        assert not await s.accept_audio('AA==')
        await s.close()
    asyncio.run(scenario())


def test_followup_revoked_before_create_is_terminal_without_dispatch():
    async def scenario():
        s = None
        updates = 0
        async def provider(event):
            nonlocal updates
            if event['type'] == 'session.update':
                updates += 1
                if updates == 2:
                    s.protocol.revoke(s.protocol.current.id)
        s, _, browser, sent = make(provider=provider)
        await s.accept_text('question')
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {
            'id': 'p1', 'status': 'completed', 'output': [
                {'type': 'function_call', 'call_id': 'c1', 'name': 'read', 'arguments': '{}'}]}})
        await asyncio.wait_for(asyncio.gather(*tuple(s._tasks)), 2)
        terminal = [e for e in browser if e['type'] == 'tool_execution_finished']
        assert len(terminal) == 1 and terminal[0]['followup_requested'] is False
        assert len([e for e in sent if e['type'] == 'response.create']) == 1
        assert s.current_request.phase == 'failed'
        assert s.phase == 'ready'
        await s.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('failure_at', ['tool_policy', 'tool_execution_started'])
def test_admitted_batch_records_one_outcome_and_discards_draft_when_start_transport_fails(failure_at, tmp_path):
    async def scenario():
        s, tools, browser, _ = make()
        path = tmp_path / 'trace.jsonl'
        s.trace = Trace(path)
        discarded = []
        original_discard = s.dashboard.discard
        def observe_discard(draft):
            discarded.append(draft)
            return original_discard(draft)
        s.dashboard.discard = observe_discard
        original_send = s.browser_send
        async def failing_browser(event):
            await original_send(event)
            if (failure_at == 'tool_policy' and event['type'] == 'input_policy' and
                    event['phase'] == 'tool_executing') or event['type'] == failure_at:
                raise OSError('browser transport failed at batch start')
        s.browser_send = failing_browser
        await s.accept_text('question')
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {
            'id': 'p1', 'status': 'completed', 'output': [
                {'type': 'function_call', 'call_id': 'c1', 'name': 'chart', 'arguments': '{}'}]}})
        await asyncio.gather(*tuple(s._tasks), return_exceptions=True)
        await asyncio.sleep(0)
        await asyncio.gather(*tuple(s._tasks), return_exceptions=True)
        assert tools.calls == []
        assert len(discarded) == 1
        assert s.current_request.phase == 'failed' and s.failed.is_set()
        await s.close()
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        outcomes = [r for r in records if r['event'] == 'batch.outcome']
        assert len(outcomes) == 1
        assert outcomes[0]['data']['call_ids'] == ['c1']
        assert outcomes[0]['data']['execution_status'] == 'failed'
        assert outcomes[0]['data']['commit_status'] == 'failed'
        assert outcomes[0]['data']['state_changed'] is False
        assert len([e for e in browser if e['type'] == 'tool_execution_finished']) == 1
    asyncio.run(scenario())


def test_terminal_transport_failure_still_records_outcome_and_keeps_conflict_request_terminal(tmp_path):
    async def scenario():
        s, _, _, _ = make()
        path = tmp_path / 'trace.jsonl'
        s.trace = Trace(path)
        original_send = s.browser_send
        async def failing_terminal(event):
            if event['type'] == 'tool_execution_finished':
                raise OSError('terminal transport unavailable')
            await original_send(event)
        s.browser_send = failing_terminal
        await s.accept_text('conflicting request')
        s.dashboard.state['dashboard_revision'] = 1
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {
            'id': 'p1', 'status': 'completed', 'output': [
                {'type': 'function_call', 'call_id': 'c1', 'name': 'chart', 'arguments': '{}'}]}})
        await asyncio.gather(*tuple(s._tasks), return_exceptions=True)
        assert s.current_request.phase == 'failed'
        await s.close()
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        outcomes = [r for r in records if r['event'] == 'batch.outcome']
        assert len(outcomes) == 1
        assert outcomes[0]['data']['commit_status'] == 'conflicted'
        assert outcomes[0]['data']['call_ids'] == ['c1']
    asyncio.run(scenario())
