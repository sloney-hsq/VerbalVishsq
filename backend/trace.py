"""Versioned research events, not runtime authority.

Playback timestamps intentionally represent a server audio-dispatch proxy and a
browser natural-end acknowledgement. They are not same-clock measurements of
the physical acoustic playback duration.
"""

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import monotonic_ns
from uuid import uuid4

from .conditions import REVISION_ENABLED, require_canonical_condition


_TOKEN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')
_CORRELATION_TOKEN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
_CORRELATION_KEYS = (
    'request_id', 'response_id', 'provider_response_id', 'batch_id', 'call_id',
    'utterance_id', 'previous_request_id', 'previous_response_id',
    'root_request_id', 'parent_request_id',
)
_CONTEXT_KEYS = ('participant_id', 'trial_id', 'task_id', 'dataset_id', 'condition')
_NEVER_PERSIST = {
    'audio', 'audio_data', 'pcm', 'raw_audio', 'base64', 'api_key', 'apikey',
    'authorization', 'auth', 'credential', 'credentials', 'password', 'secret',
    'access_token', 'refresh_token', 'id_token', 'token', 'bytes',
}
_MAX_STRING = 4096
_MAX_ARGUMENTS = 4096
_MAX_ITEMS = 256
_SAFE_REASONS = {
    'new_analytical_request', 'session_failed', 'session_closed', 'asr_timeout',
    'user_stop', 'response_completed', 'natural_end', 'provider_response_failed',
    'empty_input', 'asr_failed', 'revoked', 'stale_or_revision_conflict',
    'turn_taking_busy', 'intent_revision', 'empty', 'stop',
}


@dataclass(frozen=True)
class ExperimentContext:
    session_id: str
    participant_id: str | None
    trial_id: str | None
    task_id: str | None
    dataset_id: str
    condition: str

    def __post_init__(self):
        require_canonical_condition(self.condition)
        for field in ('participant_id', 'trial_id', 'task_id'):
            value = getattr(self, field)
            if value is not None and (not isinstance(value, str) or not _TOKEN.fullmatch(value)):
                raise ValueError(f'{field} must be a valid pseudonymous token or null')
        if not isinstance(self.dataset_id, str) or not self.dataset_id or len(self.dataset_id) > 128:
            raise ValueError('dataset_id must be a non-empty adapter identifier')

    def record_fields(self):
        return {
            'session_id': self.session_id,
            'participant_id': self.participant_id,
            'trial_id': self.trial_id,
            'task_id': self.task_id,
            'dataset_id': self.dataset_id,
            'condition': self.condition,
        }

    @property
    def context_complete(self):
        return self.participant_id is not None and self.trial_id is not None and self.task_id is not None


def resolve_experiment_context(query, settings, dataset_id):
    """Validate WS/config identifiers before claiming the one-session slot."""
    def resolve_token(name):
        explicit = query.get(name)
        value = explicit if explicit is not None else settings.get(name)
        if value is None:
            return None
        if not isinstance(value, str) or not _TOKEN.fullmatch(value):
            raise ValueError(f'invalid {name}')
        return value

    for source in (query, settings):
        asserted = source.get('dataset_id')
        if asserted is not None and asserted != dataset_id:
            raise ValueError('dataset_id does not match the loaded dataset adapter')
    condition_value = query.get('condition')
    if condition_value is None:
        condition_value = settings.get('condition', REVISION_ENABLED)
    from .conditions import normalize_ingress_condition
    condition = normalize_ingress_condition(condition_value)
    if condition is None:
        raise ValueError('invalid study condition')
    return {
        'participant_id': resolve_token('participant_id'),
        'trial_id': resolve_token('trial_id'),
        'task_id': resolve_token('task_id'),
        'dataset_id': dataset_id,
        'condition': condition,
    }


class Trace:
    def __init__(self, path=None, *, condition=REVISION_ENABLED, consent=False, context=None):
        if type(consent) is not bool:
            raise ValueError('trace_consent must be a boolean')
        self._session_id = uuid4().hex
        self._condition = require_canonical_condition(condition)
        self.consent = consent
        context = dict(context or {})
        context_condition = context.pop('condition', self._condition)
        if context_condition != self._condition:
            raise ValueError('context condition must be canonical and match Trace condition')
        self._context = ExperimentContext(
            self._session_id,
            context.pop('participant_id', None),
            context.pop('trial_id', None),
            context.pop('task_id', None),
            context.pop('dataset_id', 'unknown'),
            self._condition,
        )
        if context:
            raise ValueError('unknown experiment context field')
        self._seq = 0
        self._lock = Lock()
        self._file = None
        self.failed = False
        if path:
            try:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                self._file = Path(path).open('a', encoding='utf-8')
            except OSError:
                self.failed = True
                raise
        self.record('session.started', context_complete=self.context.context_complete)

    @property
    def session_id(self):
        return self._session_id

    @property
    def condition(self):
        return self._condition

    @property
    def context(self):
        return self._context

    def _sanitize(self, value, *, key='', depth=0):
        lowered = str(key).lower()
        if (lowered in _NEVER_PERSIST or
                any(marker in lowered for marker in ('audio', 'pcm', 'base64', 'api_key', 'authorization', 'credential', 'secret', 'token'))):
            return '[redacted]'
        if (lowered in {'text', 'delta', 'rows', 'payload', 'error', 'detail'} or
                (not self.consent and lowered in {'transcript', 'arguments'})):
            return '[redacted]'
        if depth > 8:
            return '[depth_limited]'
        if isinstance(value, bytes):
            return '[redacted]'
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, str):
            if lowered == 'reason' and value not in _SAFE_REASONS:
                return '[redacted]'
            if key == 'arguments':
                if not self.consent:
                    return '[redacted]'
                if len(value) > _MAX_ARGUMENTS:
                    return {'code': 'arguments_too_long', 'length': _MAX_ARGUMENTS}
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError, ValueError, OverflowError, RecursionError, MemoryError) as error:
                    code = ('arguments_too_complex' if isinstance(error, (OverflowError, RecursionError, MemoryError))
                            else 'invalid_arguments_json')
                    return {'code': code, 'length': min(len(value), _MAX_ARGUMENTS)}
                if not isinstance(value, (dict, list)):
                    return {'code': 'invalid_arguments_json', 'length': min(len(json.dumps(value)), _MAX_STRING)}
                return self._sanitize(value, key=key, depth=depth + 1)
            if len(value) > _MAX_STRING:
                return {'code': 'value_too_long', 'length': len(value)}
            return value
        if isinstance(value, dict):
            safe = {}
            for item_key, item_value in list(value.items())[:_MAX_ITEMS]:
                if not isinstance(item_key, str) or len(item_key) > 128:
                    continue
                safe[item_key] = self._sanitize(item_value, key=item_key, depth=depth + 1)
            if len(value) > _MAX_ITEMS:
                safe['_truncated_items'] = len(value) - _MAX_ITEMS
            return safe
        if isinstance(value, (tuple, list)):
            return [self._sanitize(item, key=key, depth=depth + 1) for item in value[:_MAX_ITEMS]]
        if value is None or type(value) is bool:
            return value
        if type(value) is int:
            return value if value.bit_length() <= 1024 else '[integer_too_large]'
        return '[unsupported]'

    def record(self, event, **data):
        with self._lock:
            self._seq += 1
            correlation = {}
            for key in _CORRELATION_KEYS:
                value = data.pop(key, None)
                correlation[key] = value if isinstance(value, str) and _CORRELATION_TOKEN.fullmatch(value) else None
            # Frozen context is top-level only; callers can never shadow it.
            for key in (*_CONTEXT_KEYS, 'session_id', 'schema_version', 'seq',
                        'observed_at', 'monotonic_ns', 'event', 'correlation', 'data'):
                data.pop(key, None)
            record = {
                'schema_version': 2,
                'seq': self._seq,
                **self._context.record_fields(),
                'observed_at': datetime.now(timezone.utc).isoformat(),
                'monotonic_ns': monotonic_ns(),
                'event': event[:128] if isinstance(event, str) else 'invalid_event',
                'correlation': correlation,
                'data': self._sanitize(data),
            }
            if self._file:
                try:
                    self._file.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n')
                    self._file.flush()
                except (OSError, TypeError, ValueError):
                    self.failed = True
            return record

    def close(self):
        with self._lock:
            if self._file:
                try:
                    self._file.close()
                except (OSError, ValueError):
                    self.failed = True
                finally:
                    self._file = None
