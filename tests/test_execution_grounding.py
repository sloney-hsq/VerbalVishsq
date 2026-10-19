"""Exercise the real runtime; only external provider/DB boundaries are doubles."""
import asyncio
import json

import pytest
from test_session import make


async def finish(session, provider_id, text):
    await session.handle_provider_event({'type': 'response.created', 'response': {'id': provider_id}})
    await session.handle_provider_event({'type': 'response.audio_transcript.delta',
                                        'response_id': provider_id, 'delta': text})
    await session.handle_provider_event({'type': 'response.done', 'response': {
        'id': provider_id, 'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'audio', 'transcript': text}]}]}})


def grounding(sent):
    prompt = [e['session']['instructions'] for e in sent if e['type'] == 'session.update'][-1]
    return json.loads(prompt.split('CURRENT EXECUTION RECORD:\n')[1])


def test_current_request_is_grounded_without_changing_user_text():
    async def run():
        s, _, _, sent = make()
        await s.accept_text('把第三张图按月显示')
        assert grounding(sent)['user_request'] == '把第三张图按月显示'
        assert grounding(sent)['latest_batch'] is None
        await s.close()
    asyncio.run(run())


@pytest.mark.parametrize('claim', ["I've changed the chart to a monthly line.",
    'The chart is now a monthly line.', "I'll take care of renaming that chart to Monthly Orders."])
@pytest.mark.parametrize('condition', ['revision_enabled', 'turn_taking'])
def test_unsupported_action_claim_requests_one_same_request_correction(claim, condition):
    async def run():
        s, tools, browser, sent = make(condition)
        await s.accept_text('Change the chart to monthly.')
        request_id = s.current_request.request_id
        await finish(s, 'p1', claim)
        assert len([e for e in sent if e['type'] == 'response.create']) == 2
        assert s.current_request.request_id == request_id
        assert not tools.calls  # Runtime must not invent a tool or arguments.
        assert any(e['type'] == 'assistant_playback_stop' for e in browser)
        assert grounding(sent)['correction'] == 'missing_action'
        await finish(s, 'p2', claim)
        assert len([e for e in sent if e['type'] == 'response.create']) == 2
        assert s.current_request.phase == 'failed'
        assert not s.failed.is_set()  # User can keep talking on this connection.
        assert any('not verified' in e.get('delta', '') for e in browser)
        await s.close()
    asyncio.run(run())


@pytest.mark.parametrize('text', [
    'Correlation does not establish causation.',
    'Would changing the chart help?',
    'I have not changed the chart.',
    'If I changed the chart, the comparison would differ.',
    'The chart could be changed to a line.',
    'I will highlight the main trade-offs. A bar chart supports categorical comparison.',
    'I will change my explanation to make it clearer.',
])
def test_discussion_and_clarification_do_not_force_calls(text):
    async def run():
        s, tools, _, sent = make()
        await s.accept_text('Could we discuss this chart?')
        await finish(s, 'p1', text)
        assert len([e for e in sent if e['type'] == 'response.create']) == 1
        assert not tools.calls
        await s.close()
    asyncio.run(run())


def test_failed_later_batch_does_not_discredit_truthful_earlier_commit():
    async def run():
        s, _, _, sent = make()
        await s.accept_text('Update the title and filter the chart')
        for provider_id, name in [('p1', 'chart'), ('p2', 'fail')]:
            await s.handle_provider_event({'type': 'response.created', 'response': {'id': provider_id}})
            await s.handle_provider_event({'type': 'response.done', 'response': {
                'id': provider_id, 'status': 'completed', 'output': [
                    {'type': 'function_call', 'name': name, 'call_id': provider_id, 'arguments': '{}'}]}})
            await asyncio.gather(*tuple(s._tasks))
        await finish(s, 'p3', 'I have updated the title. The filter could not be applied.')
        assert s.current_request.phase == 'settled'
        assert len([e for e in sent if e['type'] == 'response.create']) == 3
        assert grounding(sent)['committed_in_request']
        assert grounding(sent)['latest_batch']['commit_status'] == 'failed'
        await s.close()
    asyncio.run(run())


@pytest.mark.parametrize('claim', ['I have updated the chart.',
    'The update failed because the tool call was incomplete. I’ll fix it and switch that chart to a monthly line chart of order count.'])
def test_failed_batch_is_explicit_in_followup_and_false_success_is_corrected(claim):
    async def run():
        s, _, _, sent = make()
        await s.accept_text('Update the chart')
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {
            'id': 'p1', 'status': 'completed', 'output': [
                {'type': 'function_call', 'name': 'fail', 'call_id': 'c1', 'arguments': '{}'}]}})
        await asyncio.gather(*tuple(s._tasks))
        assert grounding(sent)['latest_batch']['commit_status'] == 'failed'
        assert grounding(sent)['latest_batch']['dashboard_revision'] == 0
        await finish(s, 'p2', claim)
        assert grounding(sent)['correction'] == 'failed_action'
        assert len([e for e in sent if e['type'] == 'response.create']) == 3
        await s.close()
    asyncio.run(run())


def test_committed_action_confirmation_does_not_reexecute():
    async def run():
        s, tools, _, sent = make()
        await s.accept_text('Create a chart')
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {
            'id': 'p1', 'status': 'completed', 'output': [
                {'type': 'function_call', 'name': 'chart', 'call_id': 'c1', 'arguments': '{}'}]}})
        await asyncio.gather(*tuple(s._tasks))
        assert grounding(sent)['latest_batch']['commit_status'] == 'committed'
        await finish(s, 'p2', 'I have created the chart.')
        assert tools.calls == ['chart']
        assert len([e for e in sent if e['type'] == 'response.create']) == 2
        await s.close()
    asyncio.run(run())


def test_new_request_does_not_inherit_old_execution_evidence():
    async def run():
        s, _, _, sent = make()
        await s.accept_text('Change the chart')
        await finish(s, 'p1', 'I have updated the chart.')
        await s.accept_text('Stop')
        await s.accept_text('Explain correlation')
        # Provider has not acknowledged the old pending generation yet.
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'old'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {
            'id': 'old', 'status': 'cancelled', 'output': []}})
        record = grounding(sent)
        assert record['user_request'] == 'Explain correlation'
        assert record['latest_batch'] is None and record['correction'] is None
        await s.close()
    asyncio.run(run())


def test_correction_can_execute_tool_and_preserves_streaming_audio():
    async def run():
        s, tools, browser, sent = make()
        await s.accept_text('Create a chart')
        await finish(s, 'p1', "I'll create the chart.")
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p2'}})
        await s.handle_provider_event({'type': 'response.audio.delta', 'response_id': 'p2', 'delta': 'pcm'})
        assert any(e['type'] == 'audio' and e['data'] == 'pcm' for e in browser)
        await s.handle_provider_event({'type': 'response.done', 'response': {
            'id': 'p2', 'status': 'completed', 'output': [
                {'type': 'function_call', 'name': 'chart', 'call_id': 'c1', 'arguments': '{}'}]}})
        await asyncio.gather(*tuple(s._tasks))
        await finish(s, 'p3', 'I have created the chart.')
        assert tools.calls == ['chart']
        assert s.dashboard.snapshot()['dashboard_revision'] == 1
        assert len([e for e in sent if e['type'] == 'response.create']) == 3
        assert s.current_request.phase == 'settled'
        await s.close()
    asyncio.run(run())


def test_stop_during_correction_dispatch_cannot_restart_generation():
    async def run():
        s, _, _, sent = make()
        original_send = s.browser_send
        async def intercept(event):
            await original_send(event)
            if event['type'] == 'assistant_playback_stop':
                # Let the send finish before delivering Stop; no browser-lock recursion.
                asyncio.get_running_loop().call_soon(lambda: asyncio.create_task(s.accept_text('Stop')))
        s.browser_send = intercept
        await s.accept_text('Create a chart')
        await finish(s, 'p1', 'I have created the chart.')
        await asyncio.sleep(.01)
        assert s.current_request.phase == 'settled'
        count = len([e for e in sent if e['type'] == 'response.create'])
        # Any dispatched correction is stale and cannot execute after Stop.
        if s._pending_ticket:
            await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p2'}})
            await s.handle_provider_event({'type': 'response.done', 'response': {
                'id': 'p2', 'status': 'completed', 'output': [
                    {'type': 'function_call', 'name': 'chart', 'call_id': 'c1', 'arguments': '{}'}]}})
        assert s.dashboard.snapshot()['dashboard_revision'] == 0
        assert len([e for e in sent if e['type'] == 'response.create']) == count
        await s.close()
    asyncio.run(run())


@pytest.mark.parametrize('name, expected', [('read', 'missing_action'), ('noop', 'unchanged_action')])
def test_read_only_or_noop_result_does_not_prove_a_new_mutation(name, expected):
    async def run():
        s, tools, _, sent = make()
        await s.accept_text('Update the chart')
        await s.handle_provider_event({'type': 'response.created', 'response': {'id': 'p1'}})
        await s.handle_provider_event({'type': 'response.done', 'response': {
            'id': 'p1', 'status': 'completed', 'output': [
                {'type': 'function_call', 'name': name, 'call_id': 'c1', 'arguments': '{}'}]}})
        await asyncio.gather(*tuple(s._tasks))
        await finish(s, 'p2', 'I have updated the chart.')
        assert grounding(sent)['correction'] == expected
        assert tools.calls == [name]
        await s.close()
    asyncio.run(run())


def test_truthful_no_change_explanation_does_not_trigger_correction():
    from refactor_next.backend.execution_grounding import ExecutionGrounding
    record = ExecutionGrounding('request', 'Use monthly')
    record.record_batch('batch', 'no_change', 0, [], [])
    assert record.contradiction('The chart is now monthly, as requested; no changes were needed.') is None
    assert record.contradiction('I have changed the chart.') == 'unchanged_action'


@pytest.mark.parametrize('new_input', ['Stop', 'Explain the difference between mean and median'])
def test_revocation_while_correction_waits_for_transport(new_input):
    async def run():
        s, tools, _, sent = make()
        entered, release = asyncio.Event(), asyncio.Event()
        original_send = s.browser_send
        async def intercept(event):
            if event.get('reason') == 'execution_claim_mismatch':
                entered.set()
                await release.wait()
            await original_send(event)
        s.browser_send = intercept
        await s.accept_text('Create a chart')
        old_id = s.current_request.request_id
        finishing = asyncio.create_task(finish(s, 'p1', 'I have created the chart.'))
        await asyncio.wait_for(entered.wait(), 1)
        accepting = asyncio.create_task(s.accept_text(new_input))
        await asyncio.sleep(0)
        release.set()
        await asyncio.wait_for(asyncio.gather(finishing, accepting), 1)
        assert not tools.calls and s.dashboard.snapshot()['dashboard_revision'] == 0
        if new_input == 'Stop':
            assert s.current_request.phase == 'settled'
            assert len([e for e in sent if e['type'] == 'response.create']) == 1
        else:
            assert s.current_request.request_id != old_id
            assert grounding(sent)['user_request'] == new_input
            assert grounding(sent)['correction'] is None
            assert len([e for e in sent if e['type'] == 'response.create']) == 2
        await s.close()
    asyncio.run(run())
