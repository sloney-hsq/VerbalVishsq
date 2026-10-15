import asyncio
import json

import pytest

from refactor_next.backend.conditions import normalize_ingress_condition
from refactor_next.backend.realtime import classify_utterance_role
from refactor_next.backend.trace import Trace

from test_session import make


@pytest.mark.parametrize(('raw', 'expected'), [
    ('turn_taking', 'turn_taking'),
    ('revision_enabled', 'revision_enabled'),
    ('half_duplex', 'turn_taking'),
    ('full_duplex_rrt', 'revision_enabled'),
])
def test_ingress_normalizes_condition(raw, expected):
    assert normalize_ingress_condition(raw) == expected


def test_internal_condition_rejects_aliases(tmp_path):
    with pytest.raises(ValueError, match='condition'):
        Trace(tmp_path / 'alias.jsonl', condition='half_duplex')
    with pytest.raises(ValueError, match='condition'):
        make('full_duplex_rrt')


@pytest.mark.parametrize(('text', 'role'), [
    ('  ', 'empty'),
    ('嗯', 'backchannel'),
    ('stop', 'stop'),
    ('改成柱状图', 'analytical_request'),
    ('只看今年', 'analytical_request'),
    ('What is the trend?', 'analytical_request'),
])
def test_utterance_roles_do_not_infer_revision_taxonomy(text, role):
    assert classify_utterance_role(text) == role


@pytest.mark.parametrize('source', ['browser', 'asr'])
def test_turn_taking_rejects_analytical_request_while_busy(source, tmp_path):
    async def scenario():
        session, _, browser, sent = make('turn_taking')
        path = tmp_path / 'trace.jsonl'
        session.trace = Trace(path, condition='turn_taking')
        await session.accept_text('first question')
        old = session.protocol.current
        epoch = session.protocol.epoch
        before = len(sent)
        await session.input_policy('tool_executing')
        if source == 'asr':
            await session.handle_provider_event({'type': 'input_audio_buffer.speech_started', 'item_id': 'utterance-2'})
            await session.handle_provider_event({
                'type': 'conversation.item.input_audio_transcription.completed',
                'item_id': 'utterance-2', 'transcript': 'new question',
            })
        else:
            await session.accept_text('new question')
        assert session.protocol.current.id == old.id
        assert session.protocol.epoch == epoch
        assert session.protocol.allowed(old.id)
        assert len(sent) == before
        assert not any(event['type'] == 'assistant_playback_stop' for event in browser)
        assert session._resolved.is_set()
        rejected = [json.loads(line) for line in path.read_text().splitlines()
                    if json.loads(line)['event'] == 'input.rejected']
        assert rejected[-1]['data']['reason'] == 'turn_taking_busy'
        await session.close()
    asyncio.run(scenario())


def test_revision_enabled_accepts_analytical_request_while_busy():
    async def scenario():
        session, _, _, _ = make('revision_enabled')
        await session.accept_text('first question')
        old = session.protocol.current
        await session.input_policy('tool_executing')
        await session.accept_text('new question')
        assert session.protocol.current.id != old.id
        assert session.protocol.epoch > old.epoch
        await session.close()
    asyncio.run(scenario())


def test_busy_typed_rejection_preserves_unresolved_asr_overlap():
    async def scenario():
        session, _, browser, _ = make('turn_taking')
        await session.accept_text('first question')
        response = session.protocol.current
        await session.handle_provider_event({'type': 'response.created', 'response': {'id': 'provider-1'}})
        await session.handle_provider_event({'type': 'input_audio_buffer.speech_started', 'item_id': 'utterance-1'})
        await session.handle_provider_event({
            'type': 'response.audio.delta', 'response_id': 'provider-1', 'delta': 'AA==',
        })
        assert session.protocol.current.authority == 'suspended'
        assert not session._resolved.is_set()
        assert len(session._held_events) == 1

        await session.accept_text('typed new question')
        assert session.protocol.current.id == response.id
        assert session._overlap_id == 'utterance-1'
        assert session.protocol.current.authority == 'suspended'
        assert not session._resolved.is_set()
        assert len(session._held_events) == 1

        await session.handle_provider_event({
            'type': 'conversation.item.input_audio_transcription.completed',
            'item_id': 'utterance-1', 'transcript': '嗯',
        })
        assert session.protocol.allowed(response.id)
        assert session._resolved.is_set()
        assert session._held_events == []
        assert any(event['type'] == 'audio' and event['response_id'] == response.id for event in browser)
        await session.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('typed_text', ['stop', '嗯', ''])
def test_accepted_typed_control_invalidates_older_asr_final(typed_text):
    async def scenario():
        session, _, _, sent = make('turn_taking')
        await session.accept_text('first question')
        await session.handle_provider_event({'type': 'response.created', 'response': {'id': 'provider-1'}})
        await session.handle_provider_event({'type': 'input_audio_buffer.speech_started', 'item_id': 'utterance-1'})
        await session.handle_provider_event({
            'type': 'response.audio.delta', 'response_id': 'provider-1', 'delta': 'AA==',
        })
        await session.accept_text(typed_text)
        assert session._overlap_id is None
        assert session._resolved.is_set()
        assert session._held_events == []
        epoch = session.protocol.epoch
        response = session.protocol.current
        assert response is None or response.authority == 'active'
        creates = len([event for event in sent if event['type'] == 'response.create'])
        await session.handle_provider_event({
            'type': 'conversation.item.input_audio_transcription.completed',
            'item_id': 'utterance-1', 'transcript': 'old analytical question',
        })
        assert session.protocol.epoch == epoch
        assert session.protocol.current == response
        assert len([event for event in sent if event['type'] == 'response.create']) == creates
        await session.close()
    asyncio.run(scenario())


def test_revision_enabled_typed_request_invalidates_older_asr_final():
    async def scenario():
        session, _, _, sent = make('revision_enabled')
        await session.accept_text('first question')
        await session.handle_provider_event({'type': 'response.created', 'response': {'id': 'provider-1'}})
        await session.handle_provider_event({'type': 'input_audio_buffer.speech_started', 'item_id': 'utterance-1'})
        await session.handle_provider_event({
            'type': 'response.audio.delta', 'response_id': 'provider-1', 'delta': 'AA==',
        })
        await session.accept_text('typed new question')
        assert session._overlap_id is None
        assert session._resolved.is_set()
        assert session._held_events == []
        accepted = session.protocol.current
        epoch = session.protocol.epoch
        creates = len([event for event in sent if event['type'] == 'response.create'])
        await session.handle_provider_event({
            'type': 'conversation.item.input_audio_transcription.completed',
            'item_id': 'utterance-1', 'transcript': 'old analytical question',
        })
        assert session.protocol.current == accepted
        assert session.protocol.epoch == epoch
        assert len([event for event in sent if event['type'] == 'response.create']) == creates
        await session.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('text', ['嗯', 'stop'])
def test_non_analytical_inputs_do_not_create_response(text):
    async def scenario():
        session, _, _, sent = make('turn_taking')
        await session.accept_text(text)
        assert session.protocol.current is None
        assert not any(event['type'] == 'response.create' for event in sent)
        await session.close()
    asyncio.run(scenario())
