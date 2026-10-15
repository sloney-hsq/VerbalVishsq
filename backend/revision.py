"""Pure, session-scoped analytical request lifecycle.

Response authority remains exclusively in ResponseProtocol. These immutable
values describe the research request chain and never authorize effects.
"""

from dataclasses import dataclass, replace


ACTIVE_PHASES = frozenset({'reasoning', 'tool_execution', 'committing', 'speaking'})
TERMINAL_PHASES = frozenset({'settled', 'superseded', 'failed'})
PHASES = ACTIVE_PHASES | TERMINAL_PHASES


def _require_id(value, field, *, optional=False):
    if optional and value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be a non-empty string')


def _require_counter(value, field):
    if type(value) is not int or value < 0:
        raise ValueError(f'{field} must be a non-negative integer')


@dataclass(frozen=True)
class RevisionEvent:
    request_id: str
    previous_request_id: str | None
    previous_response_id: str | None
    root_request_id: str
    parent_request_id: str | None
    revision_index: int
    transcript: str
    utterance_id: str
    previous_phase: str | None
    in_flight: bool
    received_at_monotonic_ns: int
    dashboard_revision: int
    revision_type: str | None = None

    def __post_init__(self):
        _require_id(self.request_id, 'request_id')
        _require_id(self.previous_request_id, 'previous_request_id', optional=True)
        _require_id(self.previous_response_id, 'previous_response_id', optional=True)
        _require_id(self.root_request_id, 'root_request_id')
        _require_id(self.parent_request_id, 'parent_request_id', optional=True)
        _require_id(self.utterance_id, 'utterance_id')
        if not isinstance(self.transcript, str):
            raise ValueError('transcript must be a string')
        if self.previous_phase is not None and self.previous_phase not in PHASES:
            raise ValueError('previous_phase must be a request phase or None')
        if type(self.in_flight) is not bool:
            raise ValueError('in_flight must be a boolean')
        _require_counter(self.revision_index, 'revision_index')
        _require_counter(self.received_at_monotonic_ns, 'received_at_monotonic_ns')
        _require_counter(self.dashboard_revision, 'dashboard_revision')
        if self.revision_type is not None and not isinstance(self.revision_type, str):
            raise ValueError('revision_type must be a string or None')


@dataclass(frozen=True)
class AnalyticalRequest:
    request_id: str
    root_request_id: str
    parent_request_id: str | None
    revision_index: int
    phase: str = 'reasoning'
    response_id: str | None = None
    terminal_reason: str | None = None

    def __post_init__(self):
        _require_id(self.request_id, 'request_id')
        _require_id(self.root_request_id, 'root_request_id')
        _require_id(self.parent_request_id, 'parent_request_id', optional=True)
        _require_id(self.response_id, 'response_id', optional=True)
        _require_counter(self.revision_index, 'revision_index')
        if self.phase not in PHASES:
            raise ValueError('phase must be a request phase')
        if self.terminal_reason is not None and not isinstance(self.terminal_reason, str):
            raise ValueError('terminal_reason must be a string or None')
        if self.phase in ACTIVE_PHASES and self.terminal_reason is not None:
            raise ValueError('terminal_reason is only valid for terminal phases')


def is_in_flight(request: AnalyticalRequest | None) -> bool:
    return bool(request and request.phase in ACTIVE_PHASES)


def new_request(previous: AnalyticalRequest | None, *, request_id: str,
                transcript: str, utterance_id: str, received_at_monotonic_ns: int,
                dashboard_revision: int) -> tuple[AnalyticalRequest, RevisionEvent]:
    if previous is not None and not isinstance(previous, AnalyticalRequest):
        raise ValueError('previous must be an AnalyticalRequest or None')
    _require_id(request_id, 'request_id')
    if previous and request_id == previous.request_id:
        raise ValueError('request_id must be new and non-empty')
    if not isinstance(transcript, str):
        raise ValueError('transcript must be a string')
    _require_id(utterance_id, 'utterance_id')
    _require_counter(received_at_monotonic_ns, 'received_at_monotonic_ns')
    _require_counter(dashboard_revision, 'dashboard_revision')
    root = previous.root_request_id if previous else request_id
    parent = previous.request_id if previous else None
    index = previous.revision_index + 1 if previous else 0
    current = AnalyticalRequest(request_id, root, parent, index)
    event = RevisionEvent(
        request_id=request_id, previous_request_id=parent,
        previous_response_id=previous.response_id if previous else None,
        root_request_id=root, parent_request_id=parent, revision_index=index,
        transcript=transcript, utterance_id=utterance_id,
        previous_phase=previous.phase if previous else None,
        in_flight=is_in_flight(previous),
        received_at_monotonic_ns=received_at_monotonic_ns,
        dashboard_revision=dashboard_revision,
    )
    return current, event


def bind_response(request: AnalyticalRequest, response_id: str) -> AnalyticalRequest:
    if not isinstance(request, AnalyticalRequest):
        raise ValueError('request must be an AnalyticalRequest')
    if request.phase in TERMINAL_PHASES:
        raise ValueError('terminal request cannot bind response')
    if not response_id:
        raise ValueError('response_id must be non-empty')
    return replace(request, response_id=response_id)


def transition(request: AnalyticalRequest, phase: str, *, terminal_reason: str | None = None) -> AnalyticalRequest:
    if not isinstance(request, AnalyticalRequest):
        raise ValueError('request must be an AnalyticalRequest')
    if request.phase not in PHASES:
        raise ValueError('request phase is invalid')
    if phase not in PHASES:
        raise ValueError('unknown request phase')
    if terminal_reason is not None and not isinstance(terminal_reason, str):
        raise ValueError('terminal_reason must be a string or None')
    if phase in ACTIVE_PHASES and terminal_reason is not None:
        raise ValueError('terminal_reason is only valid for terminal phases')
    if request.phase in TERMINAL_PHASES:
        if request.phase == phase:
            return request
        raise ValueError('terminal request cannot transition')
    if phase == request.phase and terminal_reason is None:
        return request
    return replace(request, phase=phase,
                   terminal_reason=terminal_reason if phase in TERMINAL_PHASES else None)
