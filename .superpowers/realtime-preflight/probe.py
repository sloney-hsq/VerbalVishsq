"""Synthetic speech transport probe, not a human study or browser playback test."""
import asyncio
import base64
from collections import Counter
import json
from pathlib import Path
import time
import sys
import wave
from websockets.asyncio.client import connect

ROOT = Path(__file__).parent
EXPLICIT = '--explicit' in sys.argv


async def main():
    history, counts, commits = [], Counter(), []
    async with connect('ws://127.0.0.1:8002/ws?condition=revision_enabled', proxy=None,
                       max_size=8 * 1024 * 1024, close_timeout=3) as ws:
        async def receive():
            async for raw in ws:
                e = json.loads(raw)
                history.append(e)
                counts[e['type']] += 1
                if e['type'] in {'tool_call', 'tool_result'}:
                    print(json.dumps({k:e[k] for k in ('type','name','arguments','error') if k in e}),flush=True)
                if e['type'] == 'response_done':
                    print(json.dumps({'assistant_text': ''.join(x.get('delta','') for x in history
                          if x['type']=='transcript' and x.get('response_id')==e.get('response_id'))}),flush=True)
                if e['type'] == 'dashboard_commit':
                    commits.append(e)
                if e['type'] not in {'audio', 'transcript'} or e.get('role') == 'user':
                    print(json.dumps({k: e[k] for k in ('type', 'phase', 'message', 'text', 'name',
                        'commit_status', 'dashboard_revision', 'reason') if k in e}), flush=True)
                if e['type'] == 'assistant_playback_stop' and e.get('response_id'):
                    await ws.send(json.dumps({'type':'playback_stopped', 'response_id':e['response_id'],
                                              'reason':'interrupted'}))

        receiver = asyncio.create_task(receive())
        async def wait_for(kind, start=0, timeout=40):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                for e in history[start:]:
                    if e['type'] in {'error', 'configuration_error'}:
                        raise RuntimeError(e.get('message', e['type']))
                    if e['type'] == kind:
                        return e
                if receiver.done():
                    receiver.result()
                    raise RuntimeError('Backend disconnected')
                await asyncio.sleep(.05)
            raise TimeoutError(kind)

        async def speak(name):
            with wave.open(str(ROOT / (name + '.wav')), 'rb') as wav:
                assert wav.getframerate() == 16000 and wav.getsampwidth() == 2 and wav.getnchannels() == 1
                pcm = wav.readframes(wav.getnframes())
            pcm += bytes(32000)
            for offset in range(0, len(pcm), 1280):
                await ws.send(json.dumps({'type':'audio','data':base64.b64encode(pcm[offset:offset+1280]).decode()}))
                await asyncio.sleep(.04)

        try:
            await wait_for('session_ready')
            start = len(history)
            await speak('initial')
            await wait_for('dashboard_commit', start, 55)
            await wait_for('audio', start, 40)
            # Deliberately no natural_end ACK: this probe has no real speaker.
            # Revise during the active response / outstanding playback lifecycle.
            start = len(history)
            await speak('revision-explicit' if EXPLICIT else 'revision')
            await wait_for('revision_received', start)
            await wait_for('dashboard_commit', start, 55)
            await wait_for('audio', start, 40)
            start = len(history)
            await speak('backchannel')
            await asyncio.sleep(2)
            assert not any(e['type']=='revision_received' for e in history[start:])
            start = len(history)
            await speak('stop')
            await wait_for('assistant_playback_stop', start)
            start = len(history)
            await speak('recovery-explicit' if EXPLICIT else 'recovery')
            await wait_for('dashboard_commit', start, 55)
            await wait_for('audio', start, 40)
            print(json.dumps({'synthetic_probe':'passed', 'explicit_tool_wording':EXPLICIT, 'events':dict(counts),
                              'committed_revisions':[e['dashboard_revision'] for e in commits],
                              'final_views':[{'title':v['title'],'visual':v['visual'],'source':v['source']}
                                             for v in commits[-1]['views']],
                              'microphone_tested':False,'browser_render_tested':False,
                              'speaker_playback_tested':False}),flush=True)
        finally:
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)


asyncio.run(main())
