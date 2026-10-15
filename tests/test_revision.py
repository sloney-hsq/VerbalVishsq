from dataclasses import FrozenInstanceError
from dataclasses import replace

import pytest

from refactor_next.backend.revision import (
    bind_response,
    is_in_flight,
    new_request,
    transition,
)


def request(previous=None, *, request_id='r1', response_id=None):
    return new_request(
        previous, request_id=request_id, transcript='show the trend',
        utterance_id='u1', received_at_monotonic_ns=123,
        dashboard_revision=4,
    )


def test_first_request_is_its_own_root_with_no_parent():
    current, event = request()
    assert (current.request_id, current.root_request_id, current.parent_request_id,
            current.revision_index, current.phase) == ('r1', 'r1', None, 0, 'reasoning')
    assert (event.previous_request_id, event.previous_response_id, event.previous_phase,
            event.in_flight, event.revision_type) == (None, None, None, False, None)
    assert (event.transcript, event.utterance_id, event.received_at_monotonic_ns,
            event.dashboard_revision) == ('show the trend', 'u1', 123, 4)


def test_linear_chain_uses_previous_accepted_request_even_after_settlement():
    r1, _ = request()
    r1 = bind_response(r1, 'local-1')
    r2, second = request(r1, request_id='r2')
    r2 = transition(bind_response(r2, 'local-2'), 'settled')
    r3, third = request(r2, request_id='r3')
    assert (r2.root_request_id, r2.parent_request_id, r2.revision_index) == ('r1', 'r1', 1)
    assert (r3.root_request_id, r3.parent_request_id, r3.revision_index) == ('r1', 'r2', 2)
    assert (second.previous_request_id, second.previous_response_id, second.in_flight) == ('r1', 'local-1', True)
    assert (third.previous_request_id, third.previous_response_id, third.previous_phase,
            third.in_flight) == ('r2', 'local-2', 'settled', False)


def test_followup_rebinds_response_without_changing_request_identity_or_chain():
    r1, _ = request()
    rebound = bind_response(bind_response(r1, 'initial'), 'followup')
    assert (rebound.request_id, rebound.root_request_id, rebound.parent_request_id,
            rebound.revision_index, rebound.response_id) == ('r1', 'r1', None, 0, 'followup')
    assert r1.response_id is None
    with pytest.raises(FrozenInstanceError):
        rebound.phase = 'settled'


@pytest.mark.parametrize('phase', ['reasoning', 'tool_execution', 'committing', 'speaking'])
def test_only_active_phases_are_in_flight(phase):
    r1, _ = request()
    assert is_in_flight(transition(r1, phase))


@pytest.mark.parametrize('phase', ['settled', 'superseded', 'failed'])
def test_terminal_requests_cannot_be_revived_but_repeat_terminal_is_idempotent(phase):
    r1, _ = request()
    terminal = transition(r1, phase, terminal_reason='ended')
    assert not is_in_flight(terminal)
    assert transition(terminal, phase, terminal_reason='ended') is terminal
    with pytest.raises(ValueError, match='terminal'):
        transition(terminal, 'reasoning')
    with pytest.raises(ValueError, match='terminal'):
        bind_response(terminal, 'late')


@pytest.mark.parametrize('kwargs', [
    {'request_id': ''},
    {'transcript': None},
    {'utterance_id': ''},
    {'received_at_monotonic_ns': -1},
    {'dashboard_revision': -1},
])
def test_new_request_rejects_invalid_explicit_parameters(kwargs):
    parameters = dict(request_id='r1', transcript='show the trend', utterance_id='u1',
                      received_at_monotonic_ns=123, dashboard_revision=4)
    parameters.update(kwargs)
    with pytest.raises(ValueError):
        new_request(None, **parameters)


def test_transition_rejects_invalid_source_model_and_terminal_reason_on_active_phase():
    current, _ = request()
    with pytest.raises(ValueError, match='phase'):
        transition(replace(current, phase='ready'), 'settled')
    with pytest.raises(ValueError, match='terminal_reason'):
        transition(current, 'reasoning', terminal_reason='should not stick to active phase')
