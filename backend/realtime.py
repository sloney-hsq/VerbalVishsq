"""Single-session orchestration. Dataset code never owns response authority.

Provider IDs are transport aliases, bound to locally issued generation tickets.
The provider must acknowledge manual response control before microphone input.
"""
import asyncio
import json
from dataclasses import asdict
from copy import deepcopy
from time import monotonic_ns, perf_counter
from uuid import uuid4

from .conditions import REVISION_ENABLED, TURN_TAKING, require_canonical_condition
from .prompts import build_instructions
from .execution_grounding import ExecutionGrounding
from .provider_payload import (encode_provider_event, model_tool_definitions,
                               tool_output_event, ProviderMessageTooLarge)
from .revision import bind_response, is_in_flight, new_request, transition
from .response_protocol import ResponseProtocol, ProtocolError


class ProviderContractError(RuntimeError):
    def browser_event(self):
        return {'type': 'configuration_error', 'message': str(self)}


class InitialDashboardError(ProviderContractError):
    """A dataset deployment error, distinct from provider transport failure."""

    def __init__(self, view_index, tool_error):
        self.view_index = view_index
        self.tool_error = deepcopy(tool_error) if isinstance(tool_error, dict) else {
            'code': 'tool_error',
            'message': str(tool_error or 'unknown tool error'),
        }
        message = self.tool_error.get('message') or 'unknown tool error'
        prefix = (f'Initial dashboard view {view_index} failed'
                  if view_index is not None else 'Initial dashboard configuration failed')
        super().__init__(f'{prefix}: {message}')

    def browser_event(self):
        return {
            'type': 'configuration_error',
            'code': 'initial_dashboard_error',
            'message': str(self),
            'details': {
                'view_index': self.view_index,
                'tool_error': deepcopy(self.tool_error),
            },
        }


def classify_utterance_role(text):
    """Only separate control utterances from analytical requests."""
    normalized = text.strip().lower().rstrip('。.!！?？')
    if normalized in {'嗯', '嗯嗯', '好的', '好', '明白', '对', 'ok', 'okay', 'yes', 'right', 'uh huh'}:
        return 'backchannel'
    if normalized in {'停', '停止', '停一下', '别说了', 'stop', 'stop speaking', 'cancel'}:
        return 'stop'
    if not normalized:
        return 'empty'
    return 'analytical_request'


class AnalysisSession:
    def __init__(self, dataset, browser_send, provider_send, condition, trace, *, dashboard=None, toolbox=None,
                 initial_dashboard=None, study=None, render_tracker=None, journal=None):
        require_canonical_condition(condition)
        if study is not None and study.assignment.get('condition') != condition:
            raise ProviderContractError('Formal study condition must come from the server assignment.')
        if dashboard is None:
            from .dashboard import Dashboard
            dashboard = Dashboard(dataset.description['dataset_id'], dataset.description['version'])
        if toolbox is None:
            from .tools import Toolbox
            toolbox = Toolbox(dataset, dashboard)
        self.dataset, self.dashboard, self.toolbox = dataset, dashboard, toolbox
        if initial_dashboard is not None:
            if not isinstance(initial_dashboard, list):
                raise InitialDashboardError(None, {
                    'code': 'invalid_initial_dashboard',
                    'message': 'initial_dashboard must be a list of create_chart arguments',
                })
            draft = self.dashboard.begin_draft()
            try:
                for index, arguments in enumerate(initial_dashboard, start=1):
                    result = self.toolbox.execute('create_chart', arguments, draft)
                    if not result.get('success'):
                        raise InitialDashboardError(index, result.get('error'))
                self.dashboard.commit(draft)
            except Exception:
                self.dashboard.discard(draft)
                raise
        self.protocol = ResponseProtocol()
        self.browser_send, self.provider_send = browser_send, provider_send
        self.condition, self.trace = condition, trace
        self.journal = journal
        self._journal_warning_sent = False
        self.study = study
        self.render_tracker = render_tracker or (getattr(study, 'render_tracker', None) if study is not None else None)
        self.phase = 'ready'
        self.current_request = None
        self._grounding = None
        self.requests = {}
        self._response_requests = {}
        self._policy_version = 0
        self.provider_ids = {}
        self._response_context = {}
        self._pending_ticket = None
        self._requested = None
        self._provider_active = None
        self._done_ids = set()
        self._utterances = {}  # Bounded completed/superseded utterance replay window.
        self._tasks = set()
        self._browser_lock = asyncio.Lock()
        self._provider_lock = asyncio.Lock()
        self._generation_lock = asyncio.Lock()
        self._resolved = asyncio.Event()
        self._resolved.set()
        self._seq = 0
        self._closed = False
        self._ready = False
        self._playback_response = None
        self._audio_responses = set()
        self._playback_started_responses = set()
        self._held_events = []
        self._held_bytes = 0
        self._overlap_id = None
        self._study_freeze_started = False
        self._last_rendered_revision = None
        self._study_deadline_closed = False
        self._study_deadline_response_id = None
        self._study_expiry_recorded = False
        self.failed = asyncio.Event()

    def _study_gate(self, kind):
        if self.study is None:
            return True, False
        now_ns = self.study.clock()
        first_expiry = self.study.expire_if_due(now_ns)
        if first_expiry:
            self._close_study_deadline_sync()
        if self._study_deadline_closed and not self._study_expiry_recorded:
            self._record_study_expiry()
        return self.study.check_effect(kind, now_ns), (
            self._study_deadline_closed and not self._study_freeze_started)

    def _close_study_deadline_sync(self):
        """Close both study and response gates; callers may hold protocol.guard()."""
        self._study_deadline_closed = True
        self._study_deadline_response_id = self.protocol.current.id if self.protocol.current else None
        self.protocol.revise()
        self._requested = None
        self._resolved.set()

    def _record_study_expiry(self):
        self._study_expiry_recorded = True
        self._set_request_phase('failed', terminal_reason='exploration_deadline')
        self._trace_response('intent.revoked', response_id=self._study_deadline_response_id,
                             reason='exploration_deadline')

    async def _finish_study_expiry(self):
        if self.study is None or self._study_freeze_started or not self._study_deadline_closed:
            return
        self._study_freeze_started = True
        try:
            frozen = self.study.freeze(self.dashboard.snapshot(), self._last_rendered_revision,
                                       self.study.clock(), 'exploration_deadline')
            self._flush_study_evidence()
        except Exception as error:
            frozen = {'type': 'trial.state', 'phase': 'aborted', 'freeze_status': 'failed',
                      'remaining_ms': None, 'answer_status': None,
                      'evidence_refs_ready': [], 'allowed_actions': [],
                      'error_code': getattr(error, 'code', 'study_freeze_failed')}
        # The immutable snapshot/token and readiness deadline exist before any
        # transport await. Cancellation and notification can be delayed, but
        # they cannot move the evidence boundary.
        if self._study_deadline_response_id:
            await self._emit_control('assistant_playback_stop', response_id=self._study_deadline_response_id,
                                     reason='exploration_deadline')
        if self._provider_active:
            await self._publish(self._provider_lock, self.provider_send,
                                {'event_id': uuid4().hex, 'type': 'response.cancel'})
        await self._emit_control_event(frozen)
        await self.input_policy('ready')

    async def _emit_control_event(self, event):
        async with self._browser_lock:
            if self._closed:
                return False
            self._seq += 1
            payload = dict(event, seq=self._seq)
            await self.browser_send(payload)
            self._archive_published(payload)
        self.trace.record('browser.sent', message_type=event.get('type'))
        return True

    def _archive_published(self, event):
        if self.journal is not None:
            archived = dict(event)
            rid = archived.get('response_id')
            if rid:
                archived.setdefault('provider_response_id',next(
                    (pid for pid,local in self.provider_ids.items() if local == rid),None))
            self.journal.observe(archived)
            self._check_journal()

    def _check_journal(self):
        if self.journal is not None and self.journal.failed and not self._journal_warning_sent:
            self._journal_warning_sent = True
            self.trace.record('conversation_log.failed',error_code='archive_write_failed')
            if not self._closed:
                self._spawn(self._emit_control('error',message=
                    'Session text logging failed. The conversation archive may be incomplete.'))

    async def _emit_control(self, kind, **payload):
        return await self._emit_control_event(dict(type=kind, **payload))

    async def poll_study(self):
        if self.study is None or self._closed:
            return []
        _, finish = self._study_gate('input')
        if finish:
            await self._finish_study_expiry()
        events = self.study.poll(self.study.clock())
        for event in events:
            await self._emit_control_event(event)
        return events

    def _flush_study_evidence(self):
        if self.study is not None and hasattr(self.study, 'store'):
            self._spawn(self.study.store.flush_evidence(self.study.attempt_id))

    async def _wait_authority(self, response_id):
        while not self._closed:
            response = self.protocol.current
            if not response or response.id != response_id or response.authority == 'revoked':
                return False
            if response.authority == 'active':
                return self.protocol.allowed(response_id)
            await self._wait_overlap()
        return False

    async def _publish(self, lock, callback, event, *, response_id=None,
                       batch_id=None, output_key=None, output_error=False, browser=False,
                       policy_version=None, effect_kind=None):
        while True:
            if effect_kind is not None:
                allowed, finish = self._study_gate(effect_kind)
                if not allowed:
                    if finish:
                        await self._finish_study_expiry()
                    return False
            if response_id and not await self._wait_authority(response_id):
                return False
            denied = False
            finish = False
            async with lock:
                if self._closed:
                    return False
                if policy_version is not None and policy_version != self._policy_version:
                    return False
                if effect_kind is not None:
                    allowed, finish = self._study_gate(effect_kind)
                    if not allowed:
                        denied = True
                if response_id and not self.protocol.allowed(response_id):
                    # Suspension while acquiring the lock is not revocation. Release
                    # the lock before waiting so ASR/control events can resolve it.
                    if not denied:
                        continue
                if not denied:
                    if output_key is not None and not self.protocol.consume_output(
                            response_id, batch_id, output_key, error=output_error):
                        return False
                    # No await between the final authority/deadline/once-only checks and send.
                    if browser:
                        self._seq += 1
                        event = dict(event, seq=self._seq)
                    await callback(event)
                    if browser:
                        self._archive_published(event)
                    return True
            if finish:
                await self._finish_study_expiry()
            return False

    async def emit(self, kind, *, output_key=None, output_error=False, **payload):
        rid = payload.get('response_id')
        guarded = rid if kind not in {'assistant_playback_stop', 'tool_execution_finished',
                                      'revision_received', 'response_superseded'} else None
        request_id = payload.get('request_id') or self._response_requests.get(rid)
        event = dict(type=kind, **payload)
        if request_id:
            event['request_id'] = request_id
        sent = await self._publish(self._browser_lock, self.browser_send, event,
                                  response_id=guarded, batch_id=payload.get('batch_id'),
                                  output_key=output_key, output_error=output_error, browser=True,
                                  effect_kind='analysis_output' if guarded else None)
        if sent:
            self.trace.record('browser.sent', message_type=kind, response_id=rid,
                              request_id=self._response_requests.get(rid), batch_id=payload.get('batch_id'))
        return sent

    async def send(self, event, *, response_id=None, batch_id=None, output_key=None,
                   output_error=False, effect_kind=None):
        event = dict(event_id=uuid4().hex, **event)
        encode_provider_event(event)
        return await self._publish(self._provider_lock, self.provider_send, event,
                                   response_id=response_id, batch_id=batch_id,
                                   output_key=output_key, output_error=output_error,
                                   effect_kind=effect_kind or ('analysis_output' if response_id else None))

    def _trace_response(self, event, response=None, *, response_id=None, **details):
        if response is None:
            response = self._response_context.get(response_id) if response_id else self.protocol.current
        if response is not None:
            self._response_context[response.id] = response
            while len(self._response_context) > 256:
                del self._response_context[next(iter(self._response_context))]
        local_id = response.id if response else response_id
        request_id = self._response_requests.get(local_id)
        self.trace.record(event, response_id=local_id, request_id=request_id,
                          intent_epoch=response.epoch if response else self.protocol.epoch,
                          base_revision=response.base_revision if response else None, **details)

    def _revise(self, reason):
        if self.journal is not None and self.protocol.current:
            self.journal.finish_response(self.protocol.current.id,
                'disconnected' if reason == 'session_closed' else 'interrupted')
            self._check_journal()
        self._trace_response('intent.revoked', reason=reason)
        self.protocol.revise()

    def _remember_utterance(self, item_id):
        if item_id:
            self._utterances[item_id] = None
            while len(self._utterances) > 256:
                del self._utterances[next(iter(self._utterances))]

    def _request_for_response(self, response_id):
        request = self.current_request
        return (request if response_id and request and
                self._response_requests.get(response_id) == request.request_id and
                request.response_id == response_id and is_in_flight(request) else None)

    def _set_request_phase(self, phase, *, response_id=None, terminal_reason=None):
        request = self._request_for_response(response_id) if response_id else self.current_request
        if request is None or not is_in_flight(request):
            return False
        updated = transition(request, phase, terminal_reason=terminal_reason)
        if updated is request:
            return False
        self.current_request = updated
        self.requests[updated.request_id] = updated
        self._policy_version += 1
        self.trace.record('request.phase_changed', request_id=updated.request_id,
                          response_id=updated.response_id, from_phase=request.phase,
                          to_phase=updated.phase, reason=terminal_reason)
        if updated.phase == 'settled':
            self.trace.record('request.settled', request_id=updated.request_id,
                              response_id=updated.response_id, reason=terminal_reason)
        elif updated.phase == 'failed':
            self.trace.record('request.failed', request_id=updated.request_id,
                              response_id=updated.response_id, reason=terminal_reason)
        return True

    def _bind_request_response(self, response_id):
        request = self.current_request
        if not is_in_flight(request):
            return False
        updated = bind_response(request, response_id)
        self.current_request = updated
        self.requests[updated.request_id] = updated
        self._response_requests[response_id] = updated.request_id
        while len(self._response_requests) > 256:
            del self._response_requests[next(iter(self._response_requests))]
        self._policy_version += 1
        return True

    def _wire_phase(self, fallback):
        request = self.current_request
        if is_in_flight(request):
            if request.phase in {'tool_execution', 'committing'}:
                return 'tool_executing'
            if request.phase == 'speaking':
                return 'assistant_streaming'
            return 'assistant_streaming' if self._provider_active and self.provider_ids.get(self._provider_active) == request.response_id else 'followup_generating'
        if fallback in {'connecting', 'closed', 'error', 'configuration_error'}:
            return fallback
        return 'ready'

    async def input_policy(self, phase):
        phase = self._wire_phase(phase)
        self.phase = phase
        self._policy_version += 1
        version = self._policy_version
        event = {'type': 'input_policy', 'condition': self.condition, 'phase': phase,
                 'accepts_audio': phase not in {'closed', 'error', 'configuration_error', 'connecting'} and (
                     self.condition == REVISION_ENABLED or not is_in_flight(self.current_request)) and (
                     self.study is None or self.study.check_effect('input', self.study.clock()))}
        sent = await self._publish(self._browser_lock, self.browser_send, event,
                                   browser=True, policy_version=version)
        if sent:
            self.trace.record('browser.sent', message_type='input_policy', request_id=self.current_request.request_id if self.current_request else None)

    async def configure(self, voice='Ethan'):
        await self.input_policy('connecting')
        await self.send({'type': 'session.update', 'session': {
            'modalities': ['text', 'audio'], 'voice': voice,
            'input_audio_format': 'pcm', 'output_audio_format': 'pcm',
            'input_audio_transcription': {'model': 'qwen3-asr-flash-realtime'},
            'turn_detection': {'type': 'server_vad', 'threshold': 0.5,
                               'silence_duration_ms': 600, 'create_response': False, 'interrupt_response': False},
            'instructions': build_instructions(self.dataset.description, self.toolbox.schemas(), self.dashboard.snapshot()),
            'tools': [{'type': 'function', 'function': {k: d[k] for k in ('name', 'description', 'parameters')}}
                      for d in model_tool_definitions(self.toolbox.schemas())],
        }})

    async def accept_audio(self, data):
        accepted = not self._closed and self.phase not in {'error', 'closed', 'connecting', 'configuration_error'} and (self.condition == REVISION_ENABLED or not is_in_flight(self.current_request))
        if accepted:
            accepted = await self.send({'type': 'input_audio_buffer.append', 'audio': data},
                                       effect_kind='input' if self.study is not None else None)
        else:
            self.trace.record('input.rejected', phase=self.phase)
        return accepted

    async def accept_browser_text(self, text):
        if self.study is not None:
            self.trace.record('input.rejected', reason='formal_browser_text_disabled', phase=self.phase)
            return False
        await self.accept_text(text)
        return True

    async def handle_study_event(self, event: dict):
        if self.study is None:
            return False
        from .study import StudyError
        kind = event.get('type') if isinstance(event, dict) else None
        event_id = event.get('client_event_id') if isinstance(event, dict) else None
        try:
            if kind in {'view.rendered', 'view.render_failed'}:
                outcome = self.render_tracker.ack(self.study.attempt_id, event)
                error_code = outcome.get('error_code')
                status = ('accepted' if outcome.get('accepted') else
                          'conflict' if error_code == 'client_event_conflict' else 'rejected')
                if outcome.get('accepted') and outcome.get('complete'):
                    self._last_rendered_revision = outcome.get('dashboard_revision')
                receipt = {'type': 'study.receipt', 'client_event_id': event_id,
                           'event_type': kind, 'status': status, 'receipt': outcome}
                if error_code:
                    receipt['error_code'] = error_code
                await self._emit_control_event(receipt)
                await self.poll_study()
                return bool(outcome.get('accepted'))
            result = self.study.handle_control(event, self.study.clock())
            receipt = result['receipt']
            await self._emit_control('study.receipt', client_event_id=event_id,
                                     event_type=kind, status='accepted', receipt=receipt)
            if result.get('action') == 'stop':
                await self._control_stop()
            await self._emit_control_event(result['state'])
            if kind == 'trial.start':
                await self.input_policy('ready')
            return True
        except StudyError as error:
            await self._emit_control('study.receipt', client_event_id=event_id,
                                     event_type=kind, status=('conflict' if error.code == 'idempotency_conflict' else 'rejected'),
                                     error_code=error.code)
            if error.state is not None:
                await self._emit_control_event(error.state)
            return False
        except Exception as error:
            code = getattr(error, 'code', 'study_persistence_failed')
            await self._emit_control('study.receipt', client_event_id=event_id,
                                     event_type=kind, status='rejected', error_code=code)
            return False

    async def _control_stop(self):
        old = self.protocol.current
        self._set_request_phase('settled', terminal_reason='user_stop')
        self._revise('control_stop')
        self._requested = None
        self._resolved.set()
        self._held_events = []
        self._held_bytes = 0
        if old:
            await self._emit_control('assistant_playback_stop', response_id=old.id, reason='manual_stop')
        if self._provider_active:
            await self._publish(self._provider_lock, self.provider_send,
                                {'event_id': uuid4().hex, 'type': 'response.cancel'})
        await self.input_policy('ready')

    async def playback_stopped(self, response_id, reason):
        if response_id and response_id == self._playback_response and reason == 'natural_end':
            self._playback_response = None
            # Playback ACK settles research lifecycle, not response authority.
            # A matching ACK may arrive while provider authority is suspended
            # for an overlapping utterance; ownership checks still prevent a
            # late ACK from settling a superseded request.
            if self._set_request_phase('settled', response_id=response_id, terminal_reason='natural_end'):
                self._trace_response('assistant.playback_finished', response_id=response_id,
                                     observation_source='browser_natural_end_ack')
                await self.input_policy('ready')

    async def accept_text(self, text, *, item_id=None, asr_failed=False):
        if self._closed or not isinstance(text, str):
            return
        if item_id is not None:
            if item_id != self._overlap_id or item_id in self._utterances:
                self.trace.record('asr.stale_discard', utterance_id=item_id)
                return
            self._remember_utterance(item_id)
            self._overlap_id = None
        text = text.strip()
        decision = classify_utterance_role(text)
        self.trace.record('intent.decision', transcript=text, decision=decision, utterance_id=item_id)
        if decision == 'analytical_request' and self.study is not None:
            allowed, finish = self._study_gate('input')
            if not allowed:
                if finish:
                    await self._finish_study_expiry()
                self.trace.record('input.rejected', reason='study_gate_closed', phase=self.study.phase,
                                  utterance_id=item_id)
                self.protocol.resume()
                self._resolved.set()
                self._held_events = []
                self._held_bytes = 0
                return
        if decision == 'analytical_request' and self.condition == TURN_TAKING and is_in_flight(self.current_request):
            self.trace.record('input.rejected', reason='turn_taking_busy', phase=self.current_request.phase,
                              utterance_id=item_id)
            if item_id is not None:
                self.protocol.resume()
                self._resolved.set()
                await self._release_held()
                await self._pump_response()
            return
        if item_id is None:
            self._remember_utterance(self._overlap_id)
            self._overlap_id = None
        if decision == 'backchannel':
            if self.protocol.current:
                self.protocol.resume()
            self._resolved.set()
            await self.emit('transcript', role='user', text=text, utterance_id=item_id or uuid4().hex, completed=True)
            await self._release_held()
            await self._pump_response()
            return
        utterance_id = item_id or uuid4().hex
        accepted_request_id = None
        if decision == 'analytical_request':
            previous = self.current_request
            revision = self.dashboard.snapshot()['dashboard_revision']
            request_id = uuid4().hex
            received_at_ns = self.study.clock() if self.study is not None else monotonic_ns()
            if self.study is not None:
                self.study.record_request(request_id, text, received_at_ns)
            request, received = new_request(
                previous, request_id=request_id, transcript=text,
                utterance_id=utterance_id, received_at_monotonic_ns=received_at_ns,
                dashboard_revision=revision)
            if received.in_flight:
                superseded = transition(previous, 'superseded', terminal_reason='new_analytical_request')
                self.requests[superseded.request_id] = superseded
                self.trace.record('request.phase_changed', request_id=superseded.request_id,
                                  response_id=superseded.response_id, from_phase=previous.phase,
                                  to_phase='superseded', reason='new_analytical_request')
                self.trace.record('response.superseded', request_id=previous.request_id,
                                  response_id=previous.response_id, superseding_request_id=request.request_id,
                                  previous_phase=previous.phase)
            self.current_request = request
            self._grounding = ExecutionGrounding(request.request_id, text)
            accepted_request_id = request.request_id
            self.requests[request.request_id] = request
            self._policy_version += 1
            self.trace.record('user.request_received', **asdict(received))
            self.trace.record('revision.received' if received.in_flight else 'request.received', **asdict(received))
            if received.in_flight:
                await self.emit('revision_received', request_id=request.request_id,
                                previous_request_id=previous.request_id,
                                previous_response_id=previous.response_id,
                                revision_index=request.revision_index,
                                previous_phase=previous.phase, utterance_id=utterance_id)
                await self.emit('response_superseded', request_id=previous.request_id,
                                response_id=previous.response_id,
                                superseding_request_id=request.request_id,
                                previous_phase=previous.phase)
        elif decision in {'stop', 'empty'}:
            self._set_request_phase('failed' if decision == 'empty' and item_id is not None else 'settled',
                                    terminal_reason=('asr_failed' if asr_failed else 'empty_input') if decision == 'empty' else 'user_stop')
        old = self.protocol.current
        self._revise(decision)
        accepted_epoch = self.protocol.epoch
        self._resolved.set()
        self._requested = None
        await self.emit('transcript', role='user', text=text, utterance_id=utterance_id, completed=True,
                        request_id=accepted_request_id)
        if self.protocol.epoch != accepted_epoch:
            return
        await self._release_held()
        if old:
            await self.emit('assistant_playback_stop', response_id=old.id, reason='intent_revision')
        if self._provider_active:
            await self.send({'type': 'response.cancel'})
        # Another accepted browser/ASR input can run during transport awaits.
        # Only the most recent acceptance may install/request a response.
        if self.protocol.epoch != accepted_epoch:
            return
        if decision in {'stop', 'empty'}:
            self._requested = None
            if decision == 'empty':
                await self.emit('transcript', role='user', text='[Please repeat your request]', completed=True)
            await self.input_policy('ready')
            return
        response = self.protocol.begin_response(self.dashboard.snapshot()['dashboard_revision'])
        self._bind_request_response(response.id)
        self._trace_response('response.started', response)
        # Audio is already in provider conversation; text input requires its own item.
        if item_id is None:
            await self.send({'type': 'conversation.item.create', 'item': {
                'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': text}]}}, response_id=response.id)
        if not await self._wait_authority(response.id):
            return
        self._requested = response.id
        await self.input_policy('followup_generating')
        await self._pump_response()

    async def _pump_response(self):
        async with self._generation_lock:
            rid = self._requested
            if not rid or self._pending_ticket or self._provider_active or not self.protocol.allowed(rid):
                return False
            self._requested = None
            self._pending_ticket = rid
            try:
                instructions = build_instructions(self.dataset.description, self.toolbox.schemas(), self.dashboard.snapshot())
                grounding = self._grounding_for(rid)
                if grounding:
                    instructions += grounding.instructions()
                if not await self.send({'type': 'session.update', 'session': {
                    'instructions': instructions}}, response_id=rid):
                    self._pending_ticket = None
                    return False
                if not await self.send({'type': 'response.create'}, response_id=rid):
                    self._pending_ticket = None
                    return False
                return True
            except Exception as error:
                # The failed ticket may be a tool follow-up response whose
                # parent batch task is still tagged with the preceding response.
                # Resolve failure here while this response still owns the
                # analytical request; the task callback cannot safely infer it.
                if self._pending_ticket == rid:
                    self._pending_ticket = None
                if self._requested == rid:
                    self._requested = None
                await self._fail(str(error) if isinstance(error, ProviderMessageTooLarge)
                                 else 'Provider could not start the response.', response_id=rid)
                raise

    def _grounding_for(self, response_id):
        record = self._grounding
        return record if record and self._request_for_response(response_id) and (
            self._response_requests.get(response_id) == record.request_id) else None

    async def _correct_unsupported_claim(self, rid, record, text):
        reason = record.contradiction(text)
        if not reason:
            return False
        self.trace.record('execution.claim_mismatch', response_id=rid,
                          request_id=record.request_id, code=reason,
                          repair_exhausted=record.repair_used)
        await self.emit('assistant_playback_stop', response_id=rid, reason='execution_claim_mismatch')
        if not await self._wait_authority(rid) or not self._grounding_for(rid):
            return True
        self._playback_response = None
        if record.repair_used:
            # A request failure is recoverable: keep the connection and input open.
            await self.emit('transcript', role='assistant', response_id=rid,
                            delta='\nExecution check: that claimed change is not verified. '
                                  'Please rely on the committed charts and tool results.')
            await self.emit('response_done', response_id=rid)
            self._set_request_phase('failed', response_id=rid, terminal_reason='execution_claim_mismatch')
            self.protocol.revoke(rid)
            await self.input_policy('ready')
            return True
        record.repair_used = True
        record.correction = reason
        followup = self.protocol.begin_response(self.dashboard.snapshot()['dashboard_revision'])
        self._bind_request_response(followup.id)
        self._set_request_phase('reasoning', response_id=followup.id)
        self._trace_response('response.started', followup)
        self._requested = followup.id
        await self.input_policy('followup_generating')
        await self._pump_response()
        return True

    def _spawn(self, coroutine, *, response_id=None):
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(lambda done: self._task_finished(done, response_id=response_id))

    def _task_finished(self, task, *, response_id=None):
        self._tasks.discard(task)
        if not self._closed and not self.failed.is_set() and not task.cancelled() and task.exception():
            self.trace.record('session.background_error', error=str(task.exception()),
                              response_id=response_id, request_id=self._response_requests.get(response_id))
            if response_id is None or self._request_for_response(response_id):
                self._spawn(self._fail(str(task.exception()), response_id=response_id))

    async def _fail(self, message, *, response_id=None):
        if response_id and not self._request_for_response(response_id):
            return
        self._set_request_phase('failed', response_id=response_id, terminal_reason='session_failed')
        self._revise('session_failed')
        self._resolved.set()
        self.phase = 'error'
        self.failed.set()
        try:
            await self.emit('error', message=message)
        except Exception:
            pass

    async def _release_held(self):
        events, self._held_events = self._held_events, []
        self._held_bytes = 0
        for event in events:
            await self.handle_provider_event(event)

    async def _overlap_timeout(self, utterance_id):
        try:
            await asyncio.wait_for(self._resolved.wait(), timeout=15)
        except TimeoutError:
            if self._overlap_id == utterance_id and not self._closed:
                self._remember_utterance(utterance_id)
                self._overlap_id = None
                self._held_events = []
                self._held_bytes = 0
                request = self.current_request
                if is_in_flight(request):
                    await self._fail('Speech transcription did not finish; repeat your request.',
                                     response_id=request.response_id)
                else:
                    # A timeout after settlement is an input failure, not a
                    # new outcome for the already completed analytical work.
                    self._revise('asr_timeout')
                    self._resolved.set()
                    await self.input_policy('ready')
                await self.emit('transcript', role='user', text='[Please repeat your request]', completed=True)

    async def handle_provider_event(self, event):
        kind = event.get('type', '')
        if kind == 'session.updated':
            if not self._ready:
                turn = event.get('session', {}).get('turn_detection', {})
                if turn.get('create_response') is not False or turn.get('interrupt_response') is not False:
                    raise ProviderContractError('Provider must acknowledge create_response=false and interrupt_response=false; this model/endpoint cannot safely run this protocol.')
                self._ready = True
                snap = self.dashboard.snapshot()
                study_state = None
                render = None
                if self.study is not None:
                    study_state = self.study.provider_ready(snap, self.study.clock())
                    self._flush_study_evidence()
                    render = study_state.get('render')
                await self.emit('init', views=snap['views'], state=snap,
                                dashboard_revision=snap['dashboard_revision'],
                                dataset=self.dataset.description, **({'render': render} if render else {}))
                await self.emit('session_ready')
                if study_state is not None:
                    await self._emit_control_event(study_state)
                await self.input_policy('ready')
            return
        if kind == 'error':
            code = event.get('error', {}).get('code')
            if code in {'response_cancel_not_active', 'response_not_active'}:
                self.trace.record('provider.cancel_race', code=code)
                return
            raise ProviderContractError(str(event.get('error', {}).get('message', 'Provider error')))
        if kind == 'input_audio_buffer.speech_started':
            item_id = event.get('item_id')
            if not item_id:
                raise ProviderContractError('Speech events must carry an utterance item_id.')
            if item_id in self._utterances or item_id == self._overlap_id:
                return
            self._remember_utterance(self._overlap_id)
            self.protocol.suspend()
            self._resolved.clear()
            self._overlap_id = item_id
            self._spawn(self._overlap_timeout(self._overlap_id))
            self.trace.record('speech.started', utterance_id=event.get('item_id'))
            await self.emit('speech_started', utterance_id=event.get('item_id'))
            return
        if kind == 'input_audio_buffer.speech_stopped':
            await self.emit('speech_stopped', utterance_id=event.get('item_id'))
            return
        if kind == 'conversation.item.input_audio_transcription.completed':
            if event.get('item_id'):
                await self.accept_text(event.get('transcript', ''), item_id=event['item_id'])
            return
        if kind == 'conversation.item.input_audio_transcription.failed':
            if event.get('item_id'):
                await self.accept_text('', item_id=event['item_id'], asr_failed=True)
            return
        if kind.startswith('response.') and not self._resolved.is_set():
            # Keep bounded speculative speech until a backchannel/revision resolves.
            size = len(json.dumps(event))
            if self._held_bytes + size > 2_000_000:
                raise ProviderContractError('Unresolved speech overlap exceeded the bounded output buffer.')
            self._held_events.append(event)
            self._held_bytes += size
            return
        if kind == 'response.created':
            provider_id = event['response']['id']
            if provider_id in self.provider_ids:
                return
            if not self._pending_ticket:
                raise ProviderContractError('Unsolicited provider response; automatic generation must be disabled.')
            rid = self._pending_ticket
            self._pending_ticket = None
            self.provider_ids[provider_id] = rid
            self._trace_response('response.created', response_id=rid,
                                 provider_response_id=provider_id, current=self.protocol.allowed(rid))
            while len(self.provider_ids) > 256:
                old = next(iter(self.provider_ids))
                old_rid = self.provider_ids.pop(old)
                self._done_ids.discard(old)
                self._audio_responses.discard(old_rid)
            self._provider_active = provider_id
            if not self.protocol.allowed(rid):
                await self.send({'type': 'response.cancel'})
                return
            await self.emit('assistant_response_started', response_id=rid)
            await self.input_policy('assistant_streaming')
            return
        provider_id = event.get('response_id') or event.get('response', {}).get('id')
        rid = self.provider_ids.get(provider_id)
        if kind == 'response.done':
            if not rid or provider_id in self._done_ids:
                return
            self._done_ids.add(provider_id)
            if self._provider_active == provider_id:
                self._provider_active = None
            response = event['response']
            grounding = self._grounding_for(rid)
            spoken = grounding.finish_speech(rid, response) if grounding else ''
            response_status = response.get('status')
            if not isinstance(response_status, str) or response_status not in {'completed', 'cancelled', 'failed', 'incomplete'}:
                response_status = 'unknown'
            self._trace_response('response.done', response_id=rid, provider_response_id=provider_id,
                                 status=response_status, current=self.protocol.allowed(rid))
            self._trace_response('response.finished', response_id=rid, provider_response_id=provider_id,
                                 status=response_status)
            if self.journal is not None:
                self.journal.finish_response(rid,{
                    'completed':'completed','cancelled':'interrupted',
                }.get(response_status,'failed'))
                self._check_journal()
            if self.protocol.allowed(rid) or (self.protocol.current and self.protocol.current.id == rid and self.protocol.current.authority == 'suspended'):
                if response.get('status') == 'completed':
                    calls = [x for x in response.get('output', []) if x.get('type') == 'function_call']
                    if calls:
                        self._set_request_phase('tool_execution', response_id=rid)
                        self._spawn(self.run_batch(rid, calls), response_id=rid)
                    else:
                        if grounding and await self._correct_unsupported_claim(rid, grounding, spoken):
                            return
                        self._playback_response = rid if rid in self._audio_responses else None
                        await self.emit('response_done', response_id=rid)
                        if self._playback_response is None:
                            self._set_request_phase('settled', response_id=rid, terminal_reason='response_completed')
                            await self.input_policy('ready')
                        else:
                            self._set_request_phase('speaking', response_id=rid)
                else:
                    self.protocol.revoke(rid)
                    self._set_request_phase('failed', response_id=rid, terminal_reason='provider_response_failed')
                    await self.emit('assistant_playback_stop', response_id=rid, reason='provider_response_failed')
                    await self.input_policy('ready')
            await self._pump_response()
            return
        if not rid or not self.protocol.allow_output(rid):
            if provider_id:
                self.trace.record('stale.discard', provider_response_id=provider_id, message_type=kind)
            return
        if kind in {'response.audio.delta', 'response.output_audio.delta'}:
            if await self.emit('audio', response_id=rid, data=event.get('delta', ''), item_id=event.get('item_id'), content_index=event.get('content_index', 0)):
                self._audio_responses.add(rid)
                if rid not in self._playback_started_responses:
                    self._playback_started_responses.add(rid)
                    self._trace_response('assistant.playback_started', response_id=rid,
                                         observation_source='server_audio_dispatch_proxy',
                                         actual_playback_observed=False)
                self._set_request_phase('speaking', response_id=rid)
        elif kind in {'response.audio_transcript.delta', 'response.text.delta', 'response.output_audio_transcript.delta'}:
            grounding = self._grounding_for(rid)
            if grounding:
                grounding.append_speech(rid, event.get('delta', ''))
            await self.emit('transcript', role='assistant', response_id=rid, delta=event.get('delta', ''))

    async def _wait_overlap(self):
        try:
            await asyncio.wait_for(self._resolved.wait(), timeout=15)
        except TimeoutError:
            # Missing final ASR must not leave a suspended transaction hanging.
            self._set_request_phase('failed', terminal_reason='asr_timeout')
            self._revise('asr_timeout')
            self._resolved.set()
            await self.emit('transcript', role='user', text='[Please repeat your request]', completed=True)

    async def run_batch(self, response_id, calls):
        if not await self._wait_authority(response_id):
            return
        try:
            batch = self.protocol.admit(response_id, [c.get('call_id') for c in calls])
        except ProtocolError as error:
            self.trace.record('batch.rejected', reason=str(error), response_id=response_id)
            await self._fail(f'Tool batch could not be admitted: {error}', response_id=response_id)
            return
        self._set_request_phase('tool_execution', response_id=response_id)
        self._trace_response('batch.admitted', response_id=response_id, batch_id=batch.id, call_ids=list(batch.call_ids))
        draft = None
        started = perf_counter()
        results = []
        snapshot = None
        call_observations = [{'execution_status':'not_started','result_success':None,
                              'elapsed_ms':None,'started':None} for _ in calls]
        followup_requested = False
        execution_status = 'failed'
        commit_status = 'failed'
        try:
            draft = self.dashboard.begin_draft()
            await self.input_policy('tool_executing')
            try:
                changes_dashboard = any(self.toolbox.effect_category(c['name']) == 'mutating' for c in calls)
            except ValueError:
                # Unknown names are reported by execute as failed calls.
                changes_dashboard = False
            await self.emit('tool_execution_started', batch_id=batch.id, response_id=response_id,
                            tools=[{'name': c['name'], 'label': c['name']} for c in calls],
                            changes_dashboard=changes_dashboard)
            undo_mixed = len(calls) > 1 and any(c['name'] == 'undo_dashboard' for c in calls)
            for call_index, call in enumerate(calls):
                observation = call_observations[call_index]
                if not await self._wait_authority(response_id):
                    execution_status = 'failed'
                    commit_status = 'superseded'
                    return
                self.trace.record('call.started', response_id=response_id, batch_id=batch.id, call_id=call['call_id'], arguments=call.get('arguments'))
                try:
                    arguments = json.loads(call.get('arguments', '{}'))
                    if not isinstance(arguments, dict) or undo_mixed:
                        raise ValueError('Arguments must be an object; undo must be a standalone batch')
                    if results and not results[-1]['success']:
                        observation['execution_status'] = 'skipped'
                        result = {'success': False, 'payload': {},
                                  'error': {'code': 'skipped', 'message': 'Skipped after an earlier call failed.'}}
                    else:
                        call_started = perf_counter()
                        observation.update(execution_status='unobserved',started=call_started)
                        self.trace.record('tool.execution_started', response_id=response_id,
                                          request_id=self._response_requests.get(response_id),
                                          batch_id=batch.id, call_id=call['call_id'],
                                          name=call['name'], arguments=arguments)
                        try:
                            result = await asyncio.to_thread(self.toolbox.execute, call['name'], arguments, draft)
                        except Exception:
                            self.trace.record('tool.execution_finished', response_id=response_id,
                                              request_id=self._response_requests.get(response_id),
                                              batch_id=batch.id, call_id=call['call_id'],
                                              status='raised', elapsed_ms=min(86_400_000,
                                                  round((perf_counter() - call_started) * 1000)))
                            raise
                        else:
                            observation.update(execution_status='succeeded' if result.get('success') else 'failed',
                                result_success=bool(result.get('success')),
                                elapsed_ms=round((perf_counter() - call_started) * 1000,3))
                            self.trace.record('tool.execution_finished', response_id=response_id,
                                              request_id=self._response_requests.get(response_id),
                                              batch_id=batch.id, call_id=call['call_id'],
                                              status='succeeded' if isinstance(result, dict) and result.get('success') else 'failed',
                                              elapsed_ms=min(86_400_000,
                                                  round((perf_counter() - call_started) * 1000)))
                except Exception as error:
                    observation.update(execution_status='failed',result_success=False)
                    if observation['started'] is not None:
                        observation['elapsed_ms'] = round((perf_counter() - observation['started']) * 1000,3)
                    result = {'success': False, 'payload': {}, 'error': str(error)}
                results.append(result)
                self.trace.record('call.finished', response_id=response_id, batch_id=batch.id, call_id=call['call_id'], success=result['success'])
            successful = all(r['success'] for r in results)
            execution_status = 'succeeded' if successful else 'failed'
            self.protocol.finish_batch(batch.id, successful)
            if not await self._wait_authority(response_id):
                commit_status = 'superseded'
                self._trace_response('dashboard.commit_rejected', response_id=response_id, batch_id=batch.id,
                                     reason='revoked', current=False)
                self.trace.record('commit.rejected', response_id=response_id, batch_id=batch.id,
                                  intent_epoch=self.protocol.epoch, current=False, reason='revoked')
                return
            if successful:
                # Sole commit boundary: no await or arbitrary tool code inside.
                self._set_request_phase('committing', response_id=response_id)
                self._trace_response('dashboard.commit_started', response_id=response_id, batch_id=batch.id,
                                     revision=self.dashboard.snapshot()['dashboard_revision'])
                study_expired = False
                commit_now_ns = None
                with self.protocol.guard():
                    study_allowed = True
                    if self.study is not None:
                        commit_now_ns = self.study.clock()
                        study_expired = self.study.expire_if_due(commit_now_ns)
                        if study_expired:
                            self._close_study_deadline_sync()
                        study_allowed = self.study.check_effect('commit', commit_now_ns)
                    if study_allowed and self.protocol.authorize_commit(
                            batch.id, self.dashboard.snapshot()['dashboard_revision']):
                        try:
                            snapshot = self.dashboard.commit(draft)
                        except ValueError:
                            # Another installer can win Dashboard's independent CAS
                            # after the protocol's revision precheck.
                            if self.dashboard.snapshot()['dashboard_revision'] == draft.base_revision:
                                raise
                        else:
                            self.protocol.record_commit(batch.id, snapshot['dashboard_revision'])
                if study_expired:
                    self._record_study_expiry()
                    await self._finish_study_expiry()
                if snapshot is None:
                    commit_status = 'superseded' if not self.protocol.allowed(response_id) else 'conflicted'
                    self._trace_response('dashboard.commit_rejected', batch_id=batch.id, response_id=response_id,
                                         reason='stale_or_revision_conflict',
                                         current=self.protocol.allowed(response_id),
                                         revision=self.dashboard.snapshot()['dashboard_revision'])
                    self.trace.record('commit.rejected', batch_id=batch.id, response_id=response_id,
                                      intent_epoch=self.protocol.epoch, current=self.protocol.allowed(response_id),
                                      revision=self.dashboard.snapshot()['dashboard_revision'], reason='stale_or_revision_conflict')
                    if commit_status == 'conflicted':
                        self._set_request_phase('failed', response_id=response_id,
                                                terminal_reason='dashboard_revision_conflict')
                        self.protocol.revoke(response_id)
                        await self.input_policy('ready')
                    return
                commit_status = ('committed' if snapshot['dashboard_revision'] != draft.base_revision
                                 else 'no_change' if changes_dashboard else 'read_only')
                if commit_status == 'committed':
                    self._trace_response('dashboard.committed', batch_id=batch.id, revision=snapshot['dashboard_revision'], current=True)
                    render = None
                    if self.study is not None:
                        try:
                            render = self.study.register_commit(snapshot, commit_now_ns)
                            self._flush_study_evidence()
                        except Exception as error:
                            await self._fail('Study evidence could not be queued after commit.', response_id=response_id)
                            await self._emit_control('trial.state', phase='aborted', freeze_status='failed',
                                                     remaining_ms=None, answer_status=None,
                                                     evidence_refs_ready=[], allowed_actions=[],
                                                     error_code=getattr(error, 'code', 'evidence_persist_failed'))
                            return
                    if not await self.emit('dashboard_commit', response_id=response_id, batch_id=batch.id,
                                           output_key='browser:commit', dashboard_revision=snapshot['dashboard_revision'],
                                           views=snapshot['views'], state=snapshot,
                                           **({'render': render} if render else {})):
                        return
            else:
                commit_status = 'failed'
                revised = []
                for result in results:
                    if result['success']:
                        revised.append({'success': False, 'payload': {}, 'error':
                                        {'code': 'rolled_back', 'message': 'Earlier successful call was rolled back.'}})
                    else:
                        error = result.get('error', {})
                        if not isinstance(error, dict):
                            error = {'code': 'tool_error', 'message': str(error)}
                        revised.append({'success': False, 'payload': {}, 'error': error})
                results = revised
            outcome = {'execution_status': execution_status, 'commit_status': commit_status,
                       'state_changed': commit_status == 'committed'}
            grounding = self._grounding_for(response_id)
            if grounding:
                grounding.record_batch(batch.id, commit_status,
                                       self.dashboard.snapshot()['dashboard_revision'], calls, results)
            for call, result in zip(calls, results):
                if not await self.emit('tool_call', response_id=response_id, batch_id=batch.id,
                                       output_key='browser:call:' + call['call_id'], output_error=not successful,
                                       call_id=call['call_id'], name=call['name'], arguments=call.get('arguments')):
                    return
                if not await self.emit('tool_result', response_id=response_id, batch_id=batch.id,
                                       output_key='browser:result:' + call['call_id'], output_error=not successful,
                                       call_id=call['call_id'], name=call['name'], **result, **outcome):
                    return
                output = dict(result, **outcome, committed=outcome['state_changed'],
                              dashboard_revision=snapshot['dashboard_revision'] if snapshot else None)
                if not await self.send(tool_output_event(call['call_id'], output),
                       response_id=response_id, batch_id=batch.id, output_key='model:' + call['call_id'], output_error=not successful):
                    return
            if await self._wait_authority(response_id):
                followup = self.protocol.begin_response(self.dashboard.snapshot()['dashboard_revision'])
                bound = self._bind_request_response(followup.id)
                if bound:
                    self._set_request_phase('reasoning', response_id=followup.id)
                self._trace_response('response.started', followup, preceding_batch_id=batch.id)
                self._requested = followup.id
                await self.input_policy('followup_generating')
                dispatched = await self._pump_response()
                followup_requested = bool(bound and dispatched)
                if bound and not dispatched and self._request_for_response(followup.id):
                    self._set_request_phase('failed', response_id=followup.id,
                                            terminal_reason='provider_response_failed')
                    self.protocol.revoke(followup.id)
                    await self.input_policy('ready')
        finally:
            if draft is not None:
                self.dashboard.discard(draft)
            request_id = self._response_requests.get(response_id)
            owner = self.requests.get(request_id)
            if owner and owner.phase == 'superseded' and commit_status not in {'committed', 'read_only', 'no_change'}:
                commit_status = 'superseded'
            outcome = {'execution_status': execution_status, 'commit_status': commit_status,
                       'state_changed': commit_status == 'committed'}
            self.trace.record('batch.outcome', request_id=request_id, response_id=response_id,
                              batch_id=batch.id, call_ids=list(batch.call_ids),
                              **outcome, followup_requested=followup_requested)
            if self.journal is not None:
                for call, observation in zip(calls,call_observations):
                    self.journal.record_tool(call,request_id=request_id,response_id=response_id,batch_id=batch.id,
                        execution_status=observation['execution_status'],commit_status=commit_status,
                        result_success=observation['result_success'],elapsed_ms=observation['elapsed_ms'],
                        dashboard_revision=snapshot['dashboard_revision'] if snapshot is not None else None,
                        provider_response_id=next((pid for pid,local in self.provider_ids.items() if local == response_id),None))
                self._check_journal()
            await self.emit('tool_execution_finished', batch_id=batch.id, response_id=response_id,
                            duration_ms=round((perf_counter() - started) * 1000),
                            followup_requested=followup_requested, status=commit_status, **outcome)

    async def close(self):
        self._closed = True
        self._set_request_phase('failed', terminal_reason='session_closed')
        self._revise('session_closed')
        self._resolved.set()
        # Do not cancel to_thread and close DuckDB while the physical query runs.
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)
        self.trace.record('session.closed', request_id=self.current_request.request_id if self.current_request else None)
        if self.journal is not None:
            self.journal.close()
            self._check_journal()
        self.trace.close()
