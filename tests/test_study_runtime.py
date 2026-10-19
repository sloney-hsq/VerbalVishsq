import asyncio
import copy
import threading

import pytest
from contextlib import asynccontextmanager
from fastapi.testclient import TestClient

from refactor_next.backend.main import create_app
from refactor_next.backend.realtime import AnalysisSession, ProviderContractError
from refactor_next.backend.study import StudyController
from refactor_next.backend.trace import Trace


class Dataset:
    description = {"dataset_id": "test", "dataset_version": "v1"}


class Draft:
    def __init__(self, state):
        self.document = copy.deepcopy(state)
        self.base_revision = state["dashboard_revision"]
        self.dirty = False


class Dashboard:
    def __init__(self):
        self.state = {"dashboard_revision": 0, "dataset_id": "test", "dataset_version": "v1",
                      "views": [], "filters": []}

    def snapshot(self):
        return copy.deepcopy(self.state)

    def begin_draft(self):
        return Draft(self.state)

    def commit(self, draft):
        assert draft.base_revision == self.state["dashboard_revision"]
        self.state = copy.deepcopy(draft.document)
        self.state["dashboard_revision"] += int(draft.dirty)
        return self.snapshot()

    def discard(self, draft):
        pass


class Toolbox:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def schemas(self):
        return []

    def effect_category(self, name):
        return "mutating"

    def execute(self, name, arguments, draft):
        self.started.set()
        assert self.release.wait(3)
        draft.document["views"].append({"id": name, "view_revision": 1})
        draft.dirty = True
        return {"success": True, "payload": {}}


class Gate:
    def __init__(self, condition="revision_enabled"):
        self.assignment = {"condition": condition}
        self.now = 0
        self.deadline = 100
        self.open = True
        self.expired = False
        self.frozen = []
        self.commits = []
        self.requests = []
        self.phase = "exploring"

    def clock(self):
        return self.now

    def expire_if_due(self, now_ns):
        if self.open and now_ns >= self.deadline:
            self.open = False
            self.expired = True
            return True
        return False

    def check_effect(self, kind, now_ns):
        return self.open and now_ns < self.deadline

    def register_commit(self, snapshot, now_ns):
        assert self.check_effect("commit", now_ns)
        self.commits.append(copy.deepcopy(snapshot))
        return {"token": f"commit-{len(self.commits)}", "dashboard_revision": snapshot["dashboard_revision"],
                "expected_views": [], "reason": "commit"}

    def record_request(self, request_id, transcript, now_ns):
        assert self.check_effect("input", now_ns)
        self.requests.append((request_id, transcript, now_ns))

    def freeze(self, snapshot, last_rendered_revision, now_ns, reason):
        event = {"type": "trial.frozen", "state": copy.deepcopy(snapshot),
                 "dashboard_revision": snapshot["dashboard_revision"],
                 "frozen_committed_revision": snapshot["dashboard_revision"],
                 "last_rendered_revision": last_rendered_revision,
                 "render": {"token": f"frozen-{len(self.frozen) + 1}",
                            "dashboard_revision": snapshot["dashboard_revision"],
                            "expected_views": [], "reason": "frozen"},
                 "freeze_status": "pending"}
        self.phase = "answering"
        self.frozen.append(copy.deepcopy(event))
        return event

    def poll(self, now_ns):
        return []

    def state(self, now_ns, **extra):
        return {"type": "trial.state", "phase": self.phase, **extra}


def make(gate=None, condition="revision_enabled"):
    browser, provider = [], []

    async def browser_send(event):
        browser.append(event)

    async def provider_send(event):
        provider.append(event)

    dashboard, toolbox = Dashboard(), Toolbox()
    session = AnalysisSession(Dataset(), browser_send, provider_send, condition, Trace(),
                              dashboard=dashboard, toolbox=toolbox, study=gate)
    return session, toolbox, dashboard, browser, provider


def bind_response(session):
    response = session.protocol.begin_response(session.dashboard.snapshot()["dashboard_revision"])
    return response


def test_assignment_condition_is_authoritative():
    with pytest.raises(ProviderContractError, match="assignment"):
        make(Gate("turn_taking"), condition="revision_enabled")


def test_formal_browser_text_rejected_but_asr_is_accepted():
    async def scenario():
        gate = Gate()
        session, _, _, browser, provider = make(gate)

        assert await session.accept_browser_text("typed analysis") is False
        await session.handle_provider_event({"type": "input_audio_buffer.speech_started", "item_id": "spoken-1"})
        await session.handle_provider_event({
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "spoken-1", "transcript": "spoken analysis",
        })

        assert any(event["type"] == "response.create" for event in provider)
        assert any(event.get("text") == "spoken analysis" for event in browser)
        await session.close()

    asyncio.run(scenario())


def test_deadline_blocks_commit_audio_dispatch_and_asr_return():
    async def scenario():
        # Execution starts in time but cannot commit after the synchronous deadline gate.
        gate = Gate()
        session, tools, dashboard, browser, _ = make(gate)
        response = bind_response(session)
        tools.release.clear()
        batch = asyncio.create_task(session.run_batch(response.id, [
            {"call_id": "call-1", "name": "chart", "arguments": "{}"},
        ]))
        assert await asyncio.to_thread(tools.started.wait, 2)
        gate.now = gate.deadline
        tools.release.set()
        await batch
        assert dashboard.snapshot()["dashboard_revision"] == 0

        # Audio awaiting the browser lock must re-check after lock acquisition.
        gate = Gate()
        session, _, _, browser, _ = make(gate)
        response = bind_response(session)
        session.provider_ids["provider-1"] = response.id
        await session._browser_lock.acquire()
        sending = asyncio.create_task(session.handle_provider_event({
            "type": "response.audio.delta", "response_id": "provider-1", "delta": "AA==",
        }))
        await asyncio.sleep(0)
        gate.now = gate.deadline
        session._browser_lock.release()
        await sending
        assert not any(event["type"] == "audio" for event in browser)

        # Speech may start in time, but a transcript returning at the deadline cannot analyze.
        gate = Gate()
        session, _, _, _, provider = make(gate)
        await session.handle_provider_event({"type": "input_audio_buffer.speech_started", "item_id": "late-asr"})
        gate.now = gate.deadline
        await session.handle_provider_event({
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "late-asr", "transcript": "too late",
        })
        assert not any(event["type"] == "response.create" for event in provider)

        await session.close()

    asyncio.run(scenario())


def test_committed_but_unsent_state_is_frozen_and_sent_with_new_token():
    async def scenario():
        gate = Gate()
        session, tools, dashboard, browser, _ = make(gate)
        response = bind_response(session)
        tools.release.clear()
        task = asyncio.create_task(session.run_batch(response.id, [
            {"call_id": "call-1", "name": "chart", "arguments": "{}"},
        ]))
        assert await asyncio.to_thread(tools.started.wait, 2)
        await session._browser_lock.acquire()
        tools.release.set()
        for _ in range(200):
            if dashboard.snapshot()["dashboard_revision"] == 1:
                break
            await asyncio.sleep(0.005)
        assert dashboard.snapshot()["dashboard_revision"] == 1
        assert gate.commits[0]["dashboard_revision"] == 1
        gate.now = gate.deadline
        session._browser_lock.release()
        await task

        frozen = next(event for event in browser if event["type"] == "trial.frozen")
        assert frozen["state"]["dashboard_revision"] == 1
        assert frozen["state"]["views"][0]["id"] == "chart"
        assert frozen["render"]["token"] != "commit-1"
        assert not any(event["type"] == "dashboard_commit" for event in browser)
        await session.close()

    asyncio.run(scenario())


def test_deadline_freezes_before_an_occupied_send_lock_is_released():
    async def scenario():
        gate = Gate()
        session, _, _, browser, _ = make(gate)
        await session._browser_lock.acquire()
        gate.now = gate.deadline

        polling = asyncio.create_task(session.poll_study())
        for _ in range(50):
            if gate.frozen:
                break
            await asyncio.sleep(0)

        assert gate.frozen[0]["state"]["dashboard_revision"] == 0
        assert not polling.done()
        session._browser_lock.release()
        await polling
        assert any(event["type"] == "trial.frozen" for event in browser)
        await session.close()

    asyncio.run(scenario())


def test_authorized_commit_uses_its_gate_time_for_evidence_capture():
    class JumpAfterCommitGate(Gate):
        def __init__(self):
            super().__init__()
            self.after_commit_check = False

        def clock(self):
            return self.deadline if self.after_commit_check else self.deadline - 1

        def check_effect(self, kind, now_ns):
            allowed = super().check_effect(kind, now_ns)
            if kind == "commit":
                self.after_commit_check = True
            return allowed

    async def scenario():
        gate = JumpAfterCommitGate()
        session, _, dashboard, _, _ = make(gate)
        response = bind_response(session)

        await session.run_batch(response.id, [
            {"call_id": "call-1", "name": "chart", "arguments": "{}"},
        ])

        assert dashboard.snapshot()["dashboard_revision"] == 1
        assert gate.commits[0]["dashboard_revision"] == 1
        assert gate.frozen[0]["state"]["dashboard_revision"] == 1
        await session.close()

    asyncio.run(scenario())


def test_turn_taking_waits_through_followup_and_final_playback():
    async def scenario():
        session, _, _, _, _ = make(None, condition="turn_taking")
        await session.accept_text("question")
        first = session.protocol.current.id
        await session.handle_provider_event({"type": "response.created", "response": {"id": "p1"}})
        await session.handle_provider_event({"type": "response.done", "response": {
            "id": "p1", "status": "completed", "output": [
                {"type": "function_call", "call_id": "c1", "name": "chart", "arguments": "{}"},
            ],
        }})
        await asyncio.gather(*tuple(session._tasks), return_exceptions=True)
        followup = session.protocol.current.id
        assert followup != first
        assert not await session.accept_audio("AA==")
        await session.playback_stopped(first, "natural_end")
        assert not await session.accept_audio("AA==")
        await session.handle_provider_event({"type": "response.created", "response": {"id": "p2"}})
        await session.handle_provider_event({"type": "response.audio.delta", "response_id": "p2", "delta": "AA=="})
        await session.handle_provider_event({"type": "response.done", "response": {"id": "p2", "status": "completed", "output": []}})
        assert not await session.accept_audio("AA==")
        await session.playback_stopped(followup, "natural_end")
        assert await session.accept_audio("AA==")
        await session.close()

    asyncio.run(scenario())


def test_replayed_old_stop_does_not_cancel_a_new_request():
    class StopStore:
        def get_attempt(self, attempt_id):
            return {"phase": "exploring", "freeze_status": None, "answer_status": None,
                    "evidence_failure": None}

        def append_event(self, attempt_id, event, metadata, now_ns):
            pass

        def get_evidence_status(self, attempt_id):
            return {"ready_revisions": [], "pending_jobs": 0, "failed_jobs": 0,
                    "bytes_used": 0, "limit_bytes": 1, "error_code": None}

        def get_evidence_refs(self, attempt_id):
            return []

    assigned = {
        "assignment_id": "assignment-1", "participant_id": "participant-1",
        "trial_id": "trial-1", "task_id": "task-1", "condition": "revision_enabled",
        "dataset_id": "test", "study_id": "study-1", "study_version": "1",
        "manifest_sha256": "a" * 64, "is_practice": False,
        "task": {"title": "Task", "prompt": "Analyze the data.", "prompt_sha256": "b" * 64},
    }
    clock = lambda: 1
    controller = StudyController(assigned, "attempt-1", StopStore(), object(), clock=clock)
    controller.phase = "exploring"
    controller._gate_open = True
    controller.exploration_deadline_ns = 1_000

    async def scenario():
        session, _, _, _, _ = make(controller)
        await session.accept_text("first request")
        stop = {"type": "control.stop", "client_event_id": "stop-once"}
        assert await session.handle_study_event(stop) is True

        await session.accept_text("new request")
        new_request = session.current_request
        new_response = session.protocol.current
        assert new_request is not None and new_response is not None

        assert await session.handle_study_event(stop) is True

        assert session.current_request is new_request
        assert session.protocol.current is new_response
        assert new_request.phase != "settled"
        await session.close()

    asyncio.run(scenario())


def test_formal_websocket_uses_assignment_store_and_render_gate(tmp_path, monkeypatch):
    interface = tmp_path / "interface.py"
    interface.write_text('''class Data:
 def describe(self): return {"dataset_id":"olist", "version":"1", "description":"Fixture"}
 def tool_definitions(self): return []
 def execute(self, name, arguments, scope=None): raise ValueError(name)
 def close(self): pass
def open_dataset(config): return Data()
''', encoding="utf-8")
    schedule_dir = tmp_path / "schedules"
    schedule_dir.mkdir()
    assigned = {
        "assignment_id": "assignment-1", "participant_id": "participant-1",
        "trial_id": "trial-1", "task_id": "review-delivery-association",
        "condition": "revision_enabled", "dataset_id": "olist",
        "study_id": "voice-policy-between", "study_version": "1",
        "manifest_sha256": "a" * 64, "is_practice": False,
        "task": {"title": "Review and delivery", "prompt": "Investigate the association.",
                 "prompt_sha256": "b" * 64},
    }
    monkeypatch.setattr("refactor_next.backend.main.load_assignment",
                        lambda schedule_dir, assignment_id, dataset_id: copy.deepcopy(assigned)
                        if assignment_id == "assignment-1" and dataset_id == "olist"
                        else (_ for _ in ()).throw(ValueError("unknown assignment")))

    providers = []

    class Provider:
        def __init__(self):
            self.queue = asyncio.Queue()
            self.sent = []

        async def send(self, message):
            import json
            event = json.loads(message)
            self.sent.append(event)
            if event["type"] == "session.update" and "turn_detection" in event["session"]:
                await self.queue.put(json.dumps({"type": "session.updated", "session": event["session"]}))

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.queue.get()

    @asynccontextmanager
    async def connect():
        provider = Provider()
        providers.append(provider)
        yield provider

    settings = {
        "interface": str(interface), "dataset": {}, "trace_dir": str(tmp_path / "traces"),
        "study": {
            "enabled": True, "mode": "preflight", "schedule_dir": str(schedule_dir),
            "data_dir": str(tmp_path / "study-data"),
            "consent": {"transcript": True, "analysis_evidence": True, "final_answer": True},
        },
    }
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-only-not-real")
    with TestClient(create_app(settings, provider_factory=connect)) as client:
        with client.websocket_connect("/ws?assignment_id=assignment-1&condition=turn_taking") as ws:
            assert ws.receive_json()["type"] == "configuration_error"

        with client.websocket_connect("/ws?assignment_id=assignment-1") as ws:
            initial = [ws.receive_json() for _ in range(5)]
            init = next(event for event in initial if event["type"] == "init")
            preparing = next(event for event in initial if event["type"] == "trial.state")
            assert preparing["phase"] == "preparing"
            assert "task" not in preparing
            render = init["render"]
            ws.send_json({
                "type": "view.rendered", "client_event_id": "render-init",
                "render_token": render["token"], "dashboard_revision": 0,
                "view_id": None, "view_revision": None, "render_generation": 1,
                "browser_duration_ms": 0, "presentation": {"mode": "empty", "page_index": None},
            })
            seen = [ws.receive_json() for _ in range(2)]
            while not any(event.get("type") == "trial.state" and event.get("phase") == "ready" for event in seen):
                seen.append(ws.receive_json())
            ws.send_json({"type": "trial.start", "client_event_id": "start-1"})
            started = [ws.receive_json(), ws.receive_json()]
            state = next(event for event in started if event["type"] == "trial.state")
            assert state["phase"] == "exploring"
            assert state["task"]["title"] == "Review and delivery"
            ws.send_json({"type": "text", "text": "typed analysis must be rejected"})
            ws.send_json({"type": "control.stop", "client_event_id": "stop-1"})
            stopped = [ws.receive_json(), ws.receive_json()]
            assert any(event.get("type") == "study.receipt" and event.get("status") == "accepted"
                       for event in stopped)

    assert not any(event.get("type") == "conversation.item.create" for event in providers[-1].sent)

