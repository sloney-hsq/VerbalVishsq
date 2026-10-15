"""Standalone research application. Run: python -m uvicorn backend.main:app --port 8001."""
import asyncio
import json
import math
import os
import re
import anyio
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from websockets.asyncio.client import connect

from .analytics import load_dataset
from .realtime import AnalysisSession, ProviderContractError
from .trace import Trace, resolve_experiment_context

ROOT = Path(__file__).resolve().parents[1]
_ACK_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
_ACK_REASONS = {'natural_end', 'interrupted', 'manual_stop', 'intent_revision',
                'provider_response_failed', 'response_completed'}
_ACK_STAGES = {'state_projected', 'rendered', 'committed'}


def _ack_id(value):
    return value if isinstance(value, str) and _ACK_ID.fullmatch(value) else None


def _ack_counter(value):
    return value if type(value) is int and 0 <= value <= 2**53 else None


def _ack_number(value, *, maximum=600_000):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0 or value > maximum:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _safe_ack(event, session):
    """Build a new, type-specific ACK shape. Client context is never trusted."""
    kind = event.get('type')
    if not isinstance(kind, str):
        return None
    raw_response_id, raw_batch_id = event.get('response_id'), event.get('batch_id')
    response_id = _ack_id(event.get('response_id'))
    batch_id = _ack_id(event.get('batch_id'))
    safe = {'type': kind}
    if kind == 'playback_stopped':
        reason = event.get('reason')
        if response_id is None or not isinstance(reason, str) or reason not in _ACK_REASONS:
            return None
        safe.update(response_id=response_id, reason=reason)
        cursor = event.get('playback_cursor')
        if isinstance(cursor, dict):
            safe_cursor = {}
            item_id = _ack_id(cursor.get('item_id'))
            if item_id is not None:
                safe_cursor['item_id'] = item_id
            content_index = _ack_counter(cursor.get('content_index'))
            if content_index is not None:
                safe_cursor['content_index'] = content_index
            for key in ('audio_end_ms', 'current_time_ms', 'duration_ms', 'audio_time'):
                if key in cursor:
                    value = _ack_number(cursor[key], maximum=86_400_000)
                    if value is not None:
                        safe_cursor[key] = value
            if safe_cursor:
                safe['playback_cursor'] = safe_cursor
    elif kind == 'dashboard_projection_ack':
        raw_revision = event.get('revision', event.get('dashboard_revision'))
        raw_seq = event.get('seq')
        revision = _ack_counter(raw_revision)
        seq = _ack_counter(raw_seq)
        if ((raw_response_id is not None and response_id is None) or
                (raw_batch_id is not None and batch_id is None) or
                (raw_revision is not None and revision is None) or
                (raw_seq is not None and seq is None)):
            return None
        if not response_id and not batch_id:
            return None
        safe.update(response_id=response_id, batch_id=batch_id, revision=revision, client_seq=seq)
        stage = event.get('ack_stage')
        if isinstance(stage, str) and stage in _ACK_STAGES:
            safe['stage'] = stage
        digest = event.get('snapshot_digest')
        if isinstance(digest, str) and 0 < len(digest) <= 128 and re.fullmatch(r'[A-Za-z0-9_-]+', digest):
            safe['digest'] = digest
        latency = _ack_number(event.get('client_monotonic_latency_ms'))
        if latency is not None:
            safe['latency_ms'] = latency
    elif kind == 'dashboard.rendered':
        raw_revision = event.get('revision', event.get('dashboard_revision'))
        revision = _ack_counter(raw_revision)
        if ((raw_response_id is not None and response_id is None) or
                (raw_batch_id is not None and batch_id is None) or
                (raw_revision is not None and revision is None)):
            return None
        if not response_id and not batch_id and revision is None:
            return None
        safe.update(response_id=response_id, batch_id=batch_id, revision=revision)
        stage = event.get('stage')
        if isinstance(stage, str) and stage in _ACK_STAGES:
            safe['stage'] = stage
    else:
        return None
    if response_id:
        safe['request_id'] = session._response_requests.get(response_id)
    return safe


def read_config(config=None):
    if isinstance(config, dict):
        return dict(config)
    path = Path(config or os.environ.get('VERBALVIS_CONFIG', ROOT / 'configs' / 'education.json'))
    if not path.is_absolute():
        path = ROOT / path
    return json.loads(path.read_text(encoding='utf-8'))


def create_app(config=None, *, provider_factory=None):
    @asynccontextmanager
    async def lifespan(app):
        settings = read_config(config)
        interface = Path(settings['interface'])
        if not interface.is_absolute():
            interface = ROOT / interface
        data_config = dict(settings.get('dataset', {}))
        for name in ('data_dir', 'data_path'):
            if name in data_config and not Path(data_config[name]).is_absolute():
                data_config[name] = str((ROOT / data_config[name]).resolve())
        app.state.dataset = load_dataset(interface, data_config)
        app.state.settings = settings
        app.state.busy = False
        try:
            yield
        finally:
            app.state.dataset.close()

    app = FastAPI(title='VerbalVis — Dataset-adapted Full-Duplex Analytics', lifespan=lifespan)

    @app.get('/api/health')
    async def health():
        return {'status': 'ok', 'session_active': app.state.busy}

    @app.get('/api/dataset')
    async def dataset_info():
        return app.state.dataset.description

    @app.websocket('/ws')
    async def websocket(browser: WebSocket):
        await browser.accept()
        settings = app.state.settings
        try:
            experiment_context = resolve_experiment_context(
                browser.query_params, settings, app.state.dataset.description.get('dataset_id'))
            consent = settings.get('trace_consent', False)
            if type(consent) is not bool:
                raise ValueError('trace_consent must be a boolean')
        except (TypeError, ValueError):
            await browser.send_json({'type': 'configuration_error', 'message': 'Invalid experiment context or trace configuration.'})
            await browser.close(code=1008)
            return
        condition = experiment_context['condition']
        key = os.environ.get('DASHSCOPE_API_KEY')
        problem = ('Only one experiment session is allowed.' if app.state.busy else
                   'Set DASHSCOPE_API_KEY to enable live Qwen; no simulated provider is used.' if not key else None)
        if problem:
            await browser.send_json({'type': 'configuration_error', 'message': problem})
            await browser.close(code=1008)
            return
        # Single event loop, no await between checking and claiming the session.
        app.state.busy = True
        trace = None
        session = None
        tasks = []
        try:
            trace_dir = Path(settings.get('trace_dir', ROOT / 'traces'))
            if not trace_dir.is_absolute():
                trace_dir = ROOT / trace_dir
            trace = Trace(trace_dir / (uuid4().hex + '.jsonl'), condition=condition,
                          consent=consent, context=experiment_context)
            if trace.failed:
                raise RuntimeError('Research trace could not be initialized.')
            model = os.environ.get('QWEN_REALTIME_MODEL', 'qwen3.5-omni-plus-realtime')
            url = os.environ.get('QWEN_REALTIME_URL', 'wss://dashscope.aliyuncs.com/api-ws/v1/realtime')
            context = provider_factory() if provider_factory else connect(
                url + '?model=' + model, additional_headers={'Authorization': 'Bearer ' + key},
                max_size=8 * 1024 * 1024, open_timeout=20)
            async with context as provider:
                async def provider_send(event):
                    await provider.send(json.dumps(event, ensure_ascii=False, allow_nan=False))
                session = AnalysisSession(
                    app.state.dataset,
                    browser.send_json,
                    provider_send,
                    condition,
                    trace,
                    initial_dashboard=settings.get('initial_dashboard'),
                )
                await session.configure(os.environ.get('QWEN_VOICE', 'Ethan'))

                async def receive_browser():
                    while True:
                        event = await browser.receive_json()
                        if not isinstance(event, dict):
                            trace.record('browser.ack_rejected', error_code='invalid_event_shape')
                            continue
                        kind = event.get('type')
                        if not isinstance(kind, str) or len(kind) > 64:
                            trace.record('browser.ack_rejected', error_code='invalid_event_type')
                            continue
                        if kind == 'audio' and session._ready:
                            data = event.get('data')
                            if isinstance(data, str) and len(data) < 256_000:
                                await session.accept_audio(data)
                        elif kind == 'text' and session._ready:
                            await session.accept_text(event.get('text', ''))
                        elif kind in {'playback_stopped', 'dashboard_projection_ack', 'dashboard.rendered'}:
                            safe_ack = _safe_ack(event, session)
                            if safe_ack is not None:
                                trace.record('browser.ack', **safe_ack)
                                if kind == 'playback_stopped':
                                    await session.playback_stopped(safe_ack['response_id'], safe_ack['reason'])
                            else:
                                trace.record('browser.ack_rejected', error_code='invalid_ack')

                async def receive_provider():
                    async for message in provider:
                        await session.handle_provider_event(json.loads(message))

                async def monitor_trace_failure():
                    while not trace.failed:
                        await asyncio.sleep(0.05)
                    raise RuntimeError('Research trace failed; formal trial stopped.')

                tasks = [asyncio.create_task(receive_browser()), asyncio.create_task(receive_provider()),
                         asyncio.create_task(session.failed.wait()), asyncio.create_task(monitor_trace_failure())]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as error:
            if trace:
                trace.record('transport.failed', error_type=type(error).__name__)
            try:
                event = error.browser_event() if isinstance(error, ProviderContractError) else {
                    'type': 'error',
                    'message': 'Live provider connection failed; check the selected model, endpoint and credentials.',
                }
                await browser.send_json(event)
            except (RuntimeError, WebSocketDisconnect):
                pass
        finally:
            # ASGI disconnect may cancel the endpoint while DuckDB is still in a
            # worker. Finish private work before releasing the single-session slot.
            with anyio.CancelScope(shield=True):
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                try:
                    if session:
                        await session.close()
                    elif trace:
                        trace.close()
                except Exception as cleanup_error:
                    if trace:
                        try:
                            trace.record('cleanup.failed', error_type=type(cleanup_error).__name__)
                        except Exception:
                            pass
                        try:
                            trace.close()
                        except Exception:
                            pass
                finally:
                    app.state.busy = False

    build = ROOT / 'frontend' / 'dist'
    if build.is_dir():
        app.mount('/', StaticFiles(directory=build, html=True), name='frontend')
    else:
        @app.get('/')
        async def no_build():
            return JSONResponse({'message': 'Run npm ci && npm run build in frontend, then restart; or use Vite on port 5174.'})
    return app


app = create_app()
