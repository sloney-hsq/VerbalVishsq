from copy import deepcopy

import pytest

from refactor_next.backend.study import StudyController, StudyError
from refactor_next.backend.render_tracker import RenderTracker
from refactor_next.backend.study_store import StudyStore, StudyStoreError


def assignment(condition="revision_enabled"):
    return {
        "assignment_id": "assignment-1",
        "participant_id": "participant-1",
        "trial_id": "trial-1",
        "task_id": "review-delivery-association",
        "condition": condition,
        "dataset_id": "olist",
        "study_id": "voice-policy-between",
        "study_version": "1",
        "manifest_sha256": "a" * 64,
        "is_practice": False,
        "task": {
            "title": "Review and delivery time",
            "prompt": "Investigate the stated association.",
            "prompt_sha256": "b" * 64,
        },
    }


def snapshot(revision=2):
    return {
        "dashboard_revision": revision,
        "dataset_id": "olist",
        "dataset_version": "2026-10",
        "views": [{"id": "view-1", "view_revision": revision, "data": [{"x": 1}]}],
        "filters": [],
    }


class FakeStore:
    def __init__(self):
        self.attempt = {"phase": "preparing", "status": "active", "task_exposed": False,
                        "evidence_failure": None}
        self.events = []
        self.ready = set()
        self.enqueued = []
        self.draft = None

    def get_attempt(self, attempt_id):
        return deepcopy(self.attempt)

    def apply_event(self, attempt_id, client_event_id, event_type, payload):
        self.events.append((client_event_id, event_type, deepcopy(payload)))
        if event_type == "trial.ready":
            self.attempt["phase"] = "ready"
        elif event_type == "trial.start":
            self.attempt["phase"] = "exploring"
        elif event_type == "trial.task_presented":
            self.attempt["task_exposed"] = True
        elif event_type == "trial.freeze":
            self.attempt["phase"] = "answering"
            self.attempt["freeze_status"] = "pending"
        elif event_type == "trial.answering":
            self.attempt["freeze_status"] = "ready"
        elif event_type == "answer.save":
            self.draft = deepcopy(payload)
        elif event_type == "answer.submit":
            self.attempt.update(phase="completed", status="completed")
            return self._receipt(attempt_id, client_event_id, event_type, answer_status="submitted")
        elif event_type == "answer.timeout":
            self.attempt.update(phase="completed", status="completed")
            status = "partial" if self.draft and any(self.draft.get(k) for k in ("conclusion", "limitations")) else "empty"
            return self._receipt(attempt_id, client_event_id, event_type, answer_status=status)
        elif event_type == "trial.abort":
            self.attempt.update(phase="aborted", status="aborted")
        return self._receipt(attempt_id, client_event_id, event_type)

    def _receipt(self, attempt_id, client_event_id, event_type, **extra):
        return {"attempt_id": attempt_id, "client_event_id": client_event_id,
                "event_type": event_type, "phase": self.attempt["phase"],
                "status": "accepted", **extra}

    def append_event(self, attempt_id, event, metadata, now_ns):
        self.events.append(("journal", event, deepcopy(metadata)))

    def enqueue_evidence(self, attempt_id, snap, provenance):
        self.enqueued.append(deepcopy(snap))
        return f"job-{len(self.enqueued)}"

    def evidence_ready(self, attempt_id, revision):
        return revision in self.ready

    def get_evidence_status(self, attempt_id):
        return {"ready_revisions": sorted(self.ready), "pending_jobs": [], "failed_jobs": [],
                "bytes_used": 0, "limit_bytes": 50 * 1024 * 1024}


class FakeRenderTracker:
    def __init__(self):
        self.registered = []
        self.states = {}

    def register(self, attempt_id, snap, reason):
        token = f"render-{len(self.registered) + 1}"
        envelope = {"token": token, "dashboard_revision": snap["dashboard_revision"],
                    "expected_views": [{"view_id": view["id"], "view_revision": view["view_revision"]}
                                       for view in snap["views"]], "reason": reason}
        self.registered.append((attempt_id, deepcopy(snap), reason, envelope))
        self.states[token] = {"accepted": True, "complete": False, "failed": False,
                              "dashboard_revision": snap["dashboard_revision"], "error_code": None}
        return deepcopy(envelope)

    def status(self, attempt_id, token):
        return deepcopy(self.states[token])


class Clock:
    def __init__(self, now=1_000_000_000):
        self.now = now

    def __call__(self):
        return self.now

    def advance_seconds(self, seconds):
        self.now += int(seconds * 1_000_000_000)


def ready_controller(*, condition="revision_enabled"):
    store, tracker, clock = FakeStore(), FakeRenderTracker(), Clock()
    controller = StudyController(assignment(condition), "attempt-1", store, tracker, clock=clock)
    preparing = controller.provider_ready(snapshot(0), clock())
    assert preparing["phase"] == "preparing"
    token = preparing["render"]["token"]
    tracker.states[token]["complete"] = True
    store.ready.add(0)
    assert controller.poll(clock())[-1]["phase"] == "ready"
    return controller, store, tracker, clock


def start(controller, clock):
    result = controller.handle_control({"type": "trial.start", "client_event_id": "start-1"}, clock())
    assert result["receipt"]["status"] == "accepted"
    return result


def test_assignment_blocks_condition_override():
    controller, _, _, clock = ready_controller()

    with pytest.raises(StudyError, match="identity"):
        controller.handle_control({"type": "trial.start", "client_event_id": "start-1",
                                   "condition": "turn_taking"}, clock())


def test_preparing_can_initialize_but_not_analyze():
    store, tracker, clock = FakeStore(), FakeRenderTracker(), Clock()
    controller = StudyController(assignment(), "attempt-1", store, tracker, clock=clock)

    assert controller.check_effect("input", clock()) is False
    initialized = controller.provider_ready(snapshot(0), clock())

    assert initialized["type"] == "trial.state"
    assert initialized["phase"] == "preparing"
    assert "task" not in initialized
    assert tracker.registered[0][2] == "init"
    assert store.enqueued[0]["dashboard_revision"] == 0
    with pytest.raises(StudyError, match="phase"):
        controller.handle_control({"type": "trial.start", "client_event_id": "early-start"}, clock())

    tracker.states[initialized["render"]["token"]]["complete"] = True
    store.ready.add(0)
    assert controller.poll(clock())[-1]["phase"] == "ready"


def test_answer_deadline_starts_after_render_and_evidence():
    controller, store, tracker, clock = ready_controller()
    start(controller, clock)
    frozen = controller.freeze(snapshot(), None, clock(), "exploration_deadline")
    token = frozen["render"]["token"]

    clock.advance_seconds(10)
    tracker.states[token]["complete"] = True
    assert controller.poll(clock()) == []
    assert controller.answer_deadline_ns is None

    store.ready.add(2)
    events = controller.poll(clock())

    assert events[-1]["type"] == "trial.state"
    assert events[-1]["phase"] == "answering"
    assert events[-1]["remaining_ms"] == 180_000
    assert controller.answer_deadline_ns == clock() + 180 * 1_000_000_000


def test_frozen_readiness_timeout_15s():
    controller, store, tracker, clock = ready_controller()
    start(controller, clock)
    controller.freeze(snapshot(), None, clock(), "exploration_deadline")

    clock.advance_seconds(15)
    events = controller.poll(clock())

    assert events[-1]["type"] == "trial.state"
    assert events[-1]["phase"] == "aborted"
    assert events[-1]["error_code"] == "frozen_readiness_timeout"
    assert store.attempt["status"] == "aborted"


def test_frozen_readiness_deadline_wins_when_ready_arrives_at_boundary():
    controller, store, tracker, clock = ready_controller()
    start(controller, clock)
    frozen = controller.freeze(snapshot(), None, clock(), "exploration_deadline")
    clock.advance_seconds(15)
    tracker.states[frozen["render"]["token"]]["complete"] = True
    store.ready.add(2)

    events = controller.poll(clock())

    assert events[-1]["phase"] == "aborted"
    assert events[-1]["error_code"] == "frozen_readiness_timeout"


def test_committed_unsent_snapshot_can_freeze_with_independent_token():
    controller, store, tracker, clock = ready_controller()
    start(controller, clock)
    committed = controller.register_commit(snapshot(2), clock())
    frozen_snapshot = snapshot(3)

    frozen = controller.freeze(frozen_snapshot, 1, clock(), "exploration_deadline")

    assert committed["token"] != frozen["render"]["token"]
    assert frozen["state"] == frozen_snapshot
    assert frozen["frozen_committed_revision"] == 3
    assert frozen["last_rendered_revision"] == 1
    assert tracker.registered[-1][1] == frozen_snapshot


def test_async_evidence_failure_aborts_while_still_exploring():
    controller, store, _, clock = ready_controller()
    start(controller, clock)
    controller.register_commit(snapshot(2), clock())
    store.attempt["evidence_failure"] = "write_failed"

    events = controller.poll(clock())

    assert events[-1]["phase"] == "aborted"
    assert events[-1]["error_code"] == "evidence_persist_failed"
    assert controller.check_effect("input", clock()) is False


def test_empty_answer_timeout_completes_instead_of_transport_failure():
    controller, store, tracker, clock = ready_controller()
    start(controller, clock)
    frozen = controller.freeze(snapshot(), None, clock(), "exploration_deadline")
    tracker.states[frozen["render"]["token"]]["complete"] = True
    store.ready.add(2)
    controller.poll(clock())
    clock.advance_seconds(180)

    events = controller.poll(clock())

    assert events[-1]["phase"] == "completed"
    assert events[-1]["answer_status"] == "empty"
    assert store.attempt["status"] == "completed"


def test_task_is_revealed_only_after_start_and_cannot_start_twice():
    controller, _, _, clock = ready_controller()

    result = start(controller, clock)

    assert result["state"]["task"] == assignment()["task"]
    with pytest.raises(StudyError, match="phase"):
        controller.handle_control({"type": "trial.start", "client_event_id": "start-2"}, clock())


def test_control_replay_is_idempotent_without_resetting_deadline():
    controller, store, _, clock = ready_controller()
    event = {"type": "trial.start", "client_event_id": "start-once"}
    first = controller.handle_control(event, clock())
    first_deadline = controller.exploration_deadline_ns
    clock.advance_seconds(3)

    replay = controller.handle_control(event, clock())

    assert replay["receipt"] == first["receipt"]
    assert replay["state"]["phase"] == "exploring"
    assert replay["state"]["remaining_ms"] == 597_000
    assert controller.exploration_deadline_ns == first_deadline
    assert len([row for row in store.events if row[1] == "trial.start"]) == 1


def test_replayed_start_returns_current_answering_and_completed_state_without_resetting_deadline():
    controller, store, tracker, clock = ready_controller()
    event = {"type": "trial.start", "client_event_id": "start-replay"}
    first = controller.handle_control(event, clock())
    frozen = controller.freeze(snapshot(), None, clock(), "exploration_deadline")
    tracker.states[frozen["render"]["token"]]["complete"] = True
    store.ready.add(2)
    controller.poll(clock())
    answer_deadline = controller.answer_deadline_ns
    clock.advance_seconds(3)

    replay = controller.handle_control(event, clock())

    assert replay["receipt"] == first["receipt"]
    assert replay["state"]["phase"] == "answering"
    assert replay["state"]["freeze_status"] == "ready"
    assert replay["state"]["remaining_ms"] == 177_000
    assert controller.answer_deadline_ns == answer_deadline

    controller.handle_control({
        "type": "answer.submit", "client_event_id": "submit-1",
        "submission_id": "submission-1", "conclusion": "done",
        "evidence_refs": [], "limitations": "",
    }, clock())
    completed_replay = controller.handle_control(event, clock())

    assert completed_replay["receipt"] == first["receipt"]
    assert completed_replay["state"]["phase"] == "completed"
    assert completed_replay["state"]["remaining_ms"] is None
    assert controller.answer_deadline_ns == answer_deadline


def test_replayed_stop_has_no_second_stop_action():
    controller, _, _, clock = ready_controller()
    start(controller, clock)
    event = {"type": "control.stop", "client_event_id": "stop-replay"}
    first = controller.handle_control(event, clock())

    replay = controller.handle_control(event, clock())

    assert first["action"] == "stop"
    assert "action" not in replay
    assert replay["receipt"] == first["receipt"]


def test_start_marks_task_exposed_before_visible_state_can_be_sent(tmp_path):
    store = StudyStore(tmp_path / "study-data")
    assigned = assignment()
    identity = {key: value for key, value in assigned.items() if key != "task"}
    consent = {"transcript": False, "analysis_evidence": True, "final_answer": True}
    provenance = {
        "git_commit": "abc123", "git_dirty": False, "model": "fixture-model",
        "prompt_sha256": "p" * 64, "tool_schema_sha256": "t" * 64,
        "dataset_version": "2026-10", "initial_dashboard_sha256": "i" * 64,
    }
    attempt = store.begin_attempt(identity, "session-1", consent, provenance)
    tracker, clock = RenderTracker(), Clock()
    controller = StudyController(assigned, attempt["attempt_id"], store, tracker, clock=clock)
    preparing = controller.provider_ready(snapshot(0), clock())
    import asyncio
    asyncio.run(store.flush_evidence(attempt["attempt_id"]))
    render = preparing["render"]
    tracker.ack(attempt["attempt_id"], {
        "type": "view.rendered", "client_event_id": "render-init-exposure",
        "render_token": render["token"], "dashboard_revision": 0,
        "view_id": "view-1", "view_revision": 0, "render_generation": 1,
        "browser_duration_ms": 1, "presentation": {"mode": "all", "page_index": None},
    })
    controller.poll(clock())

    start(controller, clock)

    assert store.get_attempt(attempt["attempt_id"])["task_exposed"] is True
    with pytest.raises(StudyStoreError, match="task_already_exposed"):
        store.begin_attempt(identity, "session-2", consent, provenance)


def test_answer_submission_at_deadline_times_out_instead():
    controller, store, tracker, clock = ready_controller()
    start(controller, clock)
    frozen = controller.freeze(snapshot(), None, clock(), "exploration_deadline")
    tracker.states[frozen["render"]["token"]]["complete"] = True
    store.ready.add(2)
    controller.poll(clock())
    clock.advance_seconds(180)

    with pytest.raises(StudyError, match="deadline"):
        controller.handle_control({
            "type": "answer.submit", "client_event_id": "late-submit",
            "submission_id": "submission-1", "conclusion": "late",
            "evidence_refs": [], "limitations": "",
        }, clock())

    assert controller.phase == "completed"
    assert controller.answer_status == "empty"


def test_unexpected_answer_persistence_failure_aborts_with_state():
    controller, store, tracker, clock = ready_controller()
    start(controller, clock)
    frozen = controller.freeze(snapshot(), None, clock(), "exploration_deadline")
    tracker.states[frozen["render"]["token"]]["complete"] = True
    store.ready.add(2)
    controller.poll(clock())
    original_apply = store.apply_event

    def fail_answer(attempt_id, client_event_id, event_type, payload):
        if event_type == "answer.submit":
            raise OSError("simulated durable write failure")
        return original_apply(attempt_id, client_event_id, event_type, payload)

    store.apply_event = fail_answer
    with pytest.raises(StudyError) as raised:
        controller.handle_control({
            "type": "answer.submit", "client_event_id": "submit-fails",
            "submission_id": "submission-fails", "conclusion": "answer",
            "evidence_refs": [], "limitations": "",
        }, clock())

    assert raised.value.code == "answer_persist_failed"
    assert raised.value.state["phase"] == "aborted"
    assert raised.value.state["error_code"] == "answer_persist_failed"
    assert controller.phase == "aborted"


def test_real_store_tracker_lifecycle_closes_the_readiness_gates(tmp_path):
    import asyncio

    store = StudyStore(tmp_path / "study-data")
    assigned = assignment()
    identity = {key: value for key, value in assigned.items() if key != "task"}
    attempt = store.begin_attempt(identity, "session-1", {
        "transcript": True, "analysis_evidence": True, "final_answer": True,
    }, {
        "git_commit": "abc123", "git_dirty": False, "model": "fixture-model",
        "prompt_sha256": "p" * 64, "tool_schema_sha256": "t" * 64,
        "dataset_version": "2026-10", "initial_dashboard_sha256": "i" * 64,
    })
    tracker, clock = RenderTracker(), Clock()
    controller = StudyController(assigned, attempt["attempt_id"], store, tracker, clock=clock)

    preparing = controller.provider_ready(snapshot(0), clock())
    asyncio.run(store.flush_evidence(attempt["attempt_id"]))
    render = preparing["render"]
    ack = tracker.ack(attempt["attempt_id"], {
        "type": "view.rendered", "client_event_id": "render-init",
        "render_token": render["token"], "dashboard_revision": 0,
        "view_id": "view-1", "view_revision": 0, "render_generation": 1,
        "browser_duration_ms": 1, "presentation": {"mode": "all", "page_index": None},
    })
    assert ack["complete"] is True
    assert controller.poll(clock())[-1]["phase"] == "ready"

    start(controller, clock)
    controller.handle_control({"type": "trial.task_presented", "client_event_id": "task-shown"}, clock())
    controller.record_request("request-1", "compare delivery and reviews", clock())
    frozen = controller.freeze(snapshot(0), 0, clock(), "exploration_deadline")
    frozen_render = frozen["render"]
    tracker.ack(attempt["attempt_id"], {
        "type": "view.rendered", "client_event_id": "render-frozen",
        "render_token": frozen_render["token"], "dashboard_revision": 0,
        "view_id": "view-1", "view_revision": 0, "render_generation": 2,
        "browser_duration_ms": 1, "presentation": {"mode": "all", "page_index": None},
    })

    state = controller.poll(clock())[-1]
    assert state["phase"] == "answering"
    assert state["freeze_status"] == "ready"
    assert state["evidence_refs_ready"][0]["revision"] == 0
    events = store.list_events(attempt["attempt_id"])
    accepted = next(row for row in events if row["event"] == "request.accepted")
    assert accepted["metadata"]["transcript"] == "compare delivery and reviews"

