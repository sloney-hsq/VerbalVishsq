"""Local synthetic ASR + real-provider logging check, not participant evidence.

No audio playback/render ACKs are fabricated. Only counts and IDs are printed.
"""
import asyncio
import base64
from collections import Counter
import json
from pathlib import Path
import wave

from websockets.asyncio.client import connect

ROOT = Path(__file__).parent


async def main():
    log_root = ROOT / 'conversation_logs'
    before = set(log_root.glob('*/conversation.jsonl'))
    ready, finished = asyncio.Event(), asyncio.Event()
    counts, transcripts, commits, errors = Counter(), [], [], []
    async with connect('ws://127.0.0.1:8002/ws?task_id=logging_preflight',
                       proxy=None,max_size=8*1024*1024,close_timeout=3) as ws:
        async def receive():
            async for raw in ws:
                event = json.loads(raw)
                kind = event['type']
                counts[kind] += 1
                if kind == 'session_ready':
                    ready.set()
                elif kind == 'transcript':
                    transcripts.append(event)
                elif kind == 'dashboard_commit':
                    commits.append(event['dashboard_revision'])
                elif kind in {'error','configuration_error'}:
                    errors.append(event.get('code','error'))
                    ready.set()
                    finished.set()
                elif kind == 'response_done':
                    finished.set()
        receiver = asyncio.create_task(receive())
        try:
            await asyncio.wait_for(ready.wait(),25)
            assert not errors, errors
            with wave.open(str(ROOT / 'initial.wav'),'rb') as wav:
                assert (wav.getframerate(),wav.getsampwidth(),wav.getnchannels()) == (16000,2,1)
                pcm = wav.readframes(wav.getnframes()) + bytes(32000)
            for offset in range(0,len(pcm),1280):
                await ws.send(json.dumps({'type':'audio','data':base64.b64encode(pcm[offset:offset+1280]).decode()}))
                await asyncio.sleep(.04)
            await asyncio.wait_for(finished.wait(),55)
            assert not errors, errors
        finally:
            receiver.cancel()
            await asyncio.gather(receiver,return_exceptions=True)
    # Wait only for endpoint cleanup; the logger flushes each completed message.
    await asyncio.sleep(.25)
    paths = set(log_root.glob('*/conversation.jsonl')) - before
    assert len(paths) == 1, 'Expected exactly one new developer-probe archive'
    path = paths.pop()
    conversation = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    tools = [json.loads(line) for line in path.with_name('tool_calls.jsonl').read_text(encoding='utf-8').splitlines()]
    users = [row for row in conversation if row['role'] == 'You']
    assistants = [row for row in conversation if row['role'] == 'AI']
    assert len(users) == 1 and assistants, 'Expected one final ASR and published assistant text'
    assert users[0]['text'] == next(e['text'] for e in transcripts if e['role'] == 'user')
    for row in assistants:
        published = ''.join(e.get('delta','') for e in transcripts if e.get('response_id') == row['response_id'])
        assert row['text'] == published
    assert tools and commits, 'Expected a real tool call and dashboard commit'
    assert all(t['request_id'] == users[0]['request_id'] and t['user_message_id'] == users[0]['message_id'] for t in tools)
    assert any(t['commit_status'] == 'committed' and t['dashboard_revision'] in commits for t in tools)
    assert all(t['session_id'] == users[0]['session_id'] for t in tools)
    print(json.dumps({'logging_probe':'passed','session_id':users[0]['session_id'],
        'conversation_messages':len(conversation),'user_messages':len(users),'assistant_messages':len(assistants),
        'tool_calls':len(tools),'committed_revisions':commits,'events':dict(counts),
        'request_and_message_links_verified':True,'published_text_matches_archive':True,
        'real_provider':True,'synthetic_audio':True,'microphone_tested':False,
        'browser_render_tested':False,'speaker_playback_tested':False},ensure_ascii=False),flush=True)


asyncio.run(main())
