"""Opt-in readable text archives. Never a source of runtime authority.

Only text successfully published to the browser enters this archive. A completed
text response does not prove the participant heard all of its audio.
"""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from time import monotonic_ns


_SECRET = re.compile(r'audio|pcm|base64|api.?key|authorization|credential|password|secret|token', re.I)
_SESSION = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$')


class ConversationLogError(RuntimeError):
    def browser_event(self):
        return {'type':'configuration_error','code':'conversation_log_unavailable',
                'message':'Session text logging could not be initialized. Check the private log directory.'}


def _safe_params(value, depth=0):
    if depth > 20:
        return '[depth_limited]'
    if isinstance(value, dict):
        return {str(k): '[redacted]' if _SECRET.search(str(k)) else _safe_params(v,depth + 1)
                for k,v in value.items()}
    if isinstance(value, list):
        return [_safe_params(v,depth + 1) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value,(str,int,float,bool)):
        return value
    return '[unsupported]'


class SessionJournal:
    def __init__(self, root, *, session_id, consent=False):
        if type(consent) is not bool or not isinstance(session_id,str) or not _SESSION.fullmatch(session_id):
            raise ValueError('Invalid conversation archive consent or session ID')
        self.directory = Path(root) / session_id
        self.session_id = session_id
        self.enabled = consent
        self.failed = False
        self._closed = False
        self._seq = 0
        self._pending = {}
        self._seen_users = set()
        self._finished_responses = set()
        self._user_messages = {}
        self._assistant_messages = {}
        self._files = {}
        if consent:
            try:
                self.directory.mkdir(parents=True,exist_ok=False)
                for name in ('conversation.jsonl','tool_calls.jsonl'):
                    self._files[name] = (self.directory / name).open('x',encoding='utf-8')
            except OSError as error:
                for stream in self._files.values():
                    stream.close()
                raise ConversationLogError('Session text logging could not be initialized.') from error

    def _write(self, name, **fields):
        if not self.enabled or self._closed or self.failed:
            return
        self._seq += 1
        record = dict(schema_version=1,ts=datetime.now(timezone.utc).isoformat(),
                      session_id=self.session_id,seq=self._seq,monotonic_ns=monotonic_ns(),**fields)
        if name == 'tool_calls.jsonl':
            record['timestamp'] = record['ts']
        try:
            self._files[name].write(json.dumps(record,ensure_ascii=False,allow_nan=False) + '\n')
            self._files[name].flush()
        except (OSError,ValueError,TypeError):
            self.failed = True

    def observe(self, event):
        if not self.enabled or self._closed or self.failed:
            return
        kind = event.get('type')
        if kind == 'transcript' and event.get('role') == 'user':
            uid, text = event.get('utterance_id'), event.get('text')
            # ASR error prompts are UI notices, not things the user said.
            if not uid or not isinstance(text,str) or not text or uid in self._seen_users:
                return
            self._seen_users.add(uid)
            message_id = 'u:' + uid
            request_id = event.get('request_id')
            if request_id:
                self._user_messages[request_id] = message_id
            self._write('conversation.jsonl',role='You',text=text,message_id=message_id,
                        request_id=request_id,response_id=None,utterance_id=uid,status='completed')
        elif kind == 'transcript' and event.get('role') == 'assistant':
            rid = event.get('response_id')
            text = event.get('delta',event.get('text'))
            if not rid or rid in self._finished_responses or not isinstance(text,str) or not text:
                return
            pending = self._pending.setdefault(rid,{
                'parts':[],'request_id':event.get('request_id'),
                'provider_response_id':event.get('provider_response_id'),
                'started_at':datetime.now(timezone.utc).isoformat(),
            })
            pending['parts'].append(text)
        elif kind in {'assistant_playback_stop','response_superseded'}:
            self.finish_response(event.get('response_id'),'interrupted')
        elif kind == 'response_done':
            self.finish_response(event.get('response_id'),'completed')

    def finish_response(self, response_id, status):
        pending = self._pending.pop(response_id,None)
        if pending is None:
            return
        self._finished_responses.add(response_id)
        message_id = 'a:' + response_id
        self._assistant_messages[response_id] = message_id
        self._write('conversation.jsonl',role='AI',text=''.join(pending['parts']),
                    message_id=message_id,request_id=pending['request_id'],response_id=response_id,
                    provider_response_id=pending['provider_response_id'],started_at=pending['started_at'],
                    status=status,delivery_scope='published_text_not_acoustic_playback')

    def record_tool(self, call, *, request_id, response_id, batch_id, execution_status,
                    commit_status, result_success, elapsed_ms, dashboard_revision,
                    provider_response_id=None, error_code=None):
        if not self.enabled or self._closed or self.failed:
            return
        params = call.get('arguments',{})
        if isinstance(params,str):
            try:
                params = json.loads(params)
            except (ValueError,RecursionError):
                params = {'_invalid_arguments':True}
        self._write('tool_calls.jsonl',tool=call.get('name'),params=_safe_params(params),
                    request_id=request_id,response_id=response_id,provider_response_id=provider_response_id,
                    batch_id=batch_id,call_id=call.get('call_id'),
                    user_message_id=self._user_messages.get(request_id),
                    assistant_message_id=self._assistant_messages.get(response_id),
                    result_success=result_success,execution_status=execution_status,
                    commit_status=commit_status,dashboard_revision=dashboard_revision,
                    cancelled=commit_status == 'superseded',error_code=error_code,
                    metrics={'tool_duration_ms':elapsed_ms})

    def close(self):
        if self._closed:
            return
        for rid in list(self._pending):
            self.finish_response(rid,'disconnected')
        for stream in self._files.values():
            try:
                stream.close()
            except (OSError,ValueError):
                self.failed = True
        self._closed = True
