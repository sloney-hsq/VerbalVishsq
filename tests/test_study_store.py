import asyncio
import json
import os
import threading
import time

import pytest

from backend.study_store import EVIDENCE_LIMIT_BYTES, StudyStore, StudyStoreError


def assignment(participant="P001"):
    return {
        "assignment_id": f"study.{participant}", "participant_id": participant,
        "trial_id": f"{participant}.formal", "task_id": "review-delivery-association",
        "condition": "revision_enabled", "dataset_id": "olist", "study_id": "study",
        "study_version": "1.0", "manifest_sha256": "a" * 64, "is_practice": False,
        "task": {"title": "Trusted", "prompt": "Trusted prompt", "prompt_sha256": "b" * 64},
    }


def consent(transcript=False):
    return {"transcript": transcript, "analysis_evidence": True, "final_answer": True}


def provenance():
    return {
        "git_commit": "a" * 40, "git_dirty": False, "model": "qwen",
        "prompt_sha256": "b" * 64, "tool_schema_sha256": "c" * 64,
        "dataset_version": "olist-v1", "initial_dashboard_sha256": "d" * 64,
    }


def event(store, attempt_id, number, kind, payload=None):
    return store.apply_event(attempt_id, f"event-{number}", kind, payload or {})


def start_and_freeze_ready(store, row=None):
    row = row or assignment()
    attempt = store.begin_attempt(row, f"session-{row['participant_id']}", consent(), provenance())
    attempt_id = attempt["attempt_id"]
    event(store, attempt_id, 1, "trial.ready")
    event(store, attempt_id, 2, "trial.start")
    event(store, attempt_id, 3, "trial.task_presented")
    event(store, attempt_id, 4, "trial.freeze", {
        "reason": "deadline", "frozen_revision": 2, "last_rendered_revision": 1,
    })
    event(store, attempt_id, 5, "trial.answering")
    return attempt_id


def answer_payload(submission_id="submission-1", evidence_refs=None):
    return {
        "submission_id": submission_id, "conclusion": "The evidence is mixed.",
        "evidence_refs": evidence_refs or [], "limitations": "Association is not causation.",
    }


def test_answer_idempotency_and_conflict(tmp_path):
    store = StudyStore(tmp_path)
    attempt_id = start_and_freeze_ready(store)
    payload = answer_payload()
    first = store.apply_event(attempt_id, "submit-event", "answer.submit", payload)
    assert first["answer_status"] == "submitted"
    assert store.apply_event(attempt_id, "submit-event", "answer.submit", payload) == first
    with pytest.raises(StudyStoreError, match="idempotency_conflict"):
        store.apply_event(attempt_id, "submit-event", "answer.submit",
                          {**payload, "conclusion": "Changed"})
    with pytest.raises(StudyStoreError, match="submission_conflict"):
        store.apply_event(attempt_id, "another-event", "answer.submit",
                          {**payload, "conclusion": "Changed"})
    assert len(store.list_answers()) == 1
    assert store.list_answers()[0]["conclusion"] == payload["conclusion"]


def test_evidence_refs_are_ready_and_attempt_local(tmp_path):
    store = StudyStore(tmp_path)
    first = start_and_freeze_ready(store)
    second = start_and_freeze_ready(store, assignment("P002"))
    job = store.enqueue_evidence(first, {"dashboard_revision": 7, "views": []},
                                 {"renderer_version": "v1"})
    ref = {"revision": 7, "artifact_id": job}
    with pytest.raises(StudyStoreError, match="evidence_not_ready"):
        store.apply_event(first, "submit-1", "answer.submit", answer_payload(evidence_refs=[ref]))
    asyncio.run(store.flush_evidence(first))
    assert store.evidence_ready(first, 7)
    assert store.get_evidence_refs(first) == [ref]
    with pytest.raises(StudyStoreError, match="evidence_not_ready"):
        store.apply_event(second, "submit-2", "answer.submit", answer_payload(evidence_refs=[ref]))
    receipt = store.apply_event(first, "submit-3", "answer.submit",
                                answer_payload(evidence_refs=[ref]))
    assert receipt["status"] == "saved"


def test_concurrent_flush_claims_each_immutable_job_once(tmp_path, monkeypatch):
    store = StudyStore(tmp_path)
    attempt_id = store.begin_attempt(assignment(), "session-flush", consent(), provenance())["attempt_id"]
    store.enqueue_evidence(attempt_id, {"dashboard_revision": 1, "views": []}, {})
    original_replace = os.replace
    calls = 0
    call_lock = threading.Lock()

    def slow_replace(source, target):
        nonlocal calls
        with call_lock:
            calls += 1
        time.sleep(0.05)
        original_replace(source, target)

    monkeypatch.setattr(os, "replace", slow_replace)

    async def flush_twice():
        await asyncio.gather(store.flush_evidence(attempt_id), store.flush_evidence(attempt_id))

    asyncio.run(flush_twice())
    assert calls == 1
    assert store.evidence_ready(attempt_id, 1)
    assert store.get_evidence_status(attempt_id)["failed_jobs"] == 0


def test_completed_survives_disconnect_and_recovery(tmp_path):
    store = StudyStore(tmp_path)
    complete = start_and_freeze_ready(store)
    store.apply_event(complete, "submit", "answer.submit", answer_payload())
    incomplete = store.begin_attempt(assignment("P002"), "session-2", consent(), provenance())["attempt_id"]
    assert store.recover_incomplete() == [incomplete]
    assert store.get_attempt(complete)["phase"] == "completed"
    assert store.get_attempt(incomplete)["phase"] == "aborted"
    with pytest.raises(StudyStoreError, match="terminal_state"):
        event(store, complete, 20, "trial.abort", {"reason_code": "disconnect"})


def test_evidence_quota_exact_limit_and_failure(tmp_path, monkeypatch):
    store = StudyStore(tmp_path)
    attempt_id = store.begin_attempt(assignment(), "session-1", consent(), provenance())["attempt_id"]
    # Canonical JSON overhead is measured independently; the artifact is exactly 50 MiB.
    base_snapshot = {"dashboard_revision": 1,
                     "views": [{"id": "quota-view", "view_revision": 1,
                                "data": [{"padding": ""}]}]}
    empty_size = len(json.dumps(base_snapshot, ensure_ascii=False,
                                sort_keys=True, separators=(",", ":")).encode("utf-8"))
    blob = "x" * (EVIDENCE_LIMIT_BYTES - empty_size)
    store.enqueue_evidence(attempt_id, {"dashboard_revision": 1,
                                        "views": [{"id": "quota-view", "view_revision": 1,
                                                   "data": [{"padding": blob}]}]}, {})
    with pytest.raises(StudyStoreError, match="evidence_limit"):
        store.enqueue_evidence(attempt_id, {"dashboard_revision": 2,
                                            "views": [{"id": "overflow", "view_revision": 1,
                                                       "data": [{"padding": "x"}]}]}, {})

    failing = StudyStore(tmp_path / "failing")
    failed_id = failing.begin_attempt(assignment(), "session-2", consent(), provenance())["attempt_id"]
    failing.enqueue_evidence(failed_id, {"dashboard_revision": 1, "views": []}, {})
    monkeypatch.setattr(os, "replace", lambda *_: (_ for _ in ()).throw(OSError("disk full")))
    asyncio.run(failing.flush_evidence(failed_id))
    assert failing.evidence_ready(failed_id, 1) is False
    assert failing.get_evidence_status(failed_id)["failed_jobs"] == 1


def test_consent_categories_are_separate(tmp_path):
    store = StudyStore(tmp_path)
    attempt_id = start_and_freeze_ready(store)
    store.append_event(attempt_id, "request.accepted", {
        "request_id": "r1", "transcript": "private words", "classification": "analytical_request"
    }, 10)
    store.apply_event(attempt_id, "submit", "answer.submit", answer_payload())
    serialized = json.dumps(store.list_events(attempt_id))
    assert "private words" not in serialized
    assert store.list_answers()[0]["conclusion"] == "The evidence is mixed."


def test_runtime_journal_vocabulary_is_strict_and_compatible(tmp_path):
    store = StudyStore(tmp_path)
    attempt_id = store.begin_attempt(assignment(), "session-journal", consent(True), provenance())["attempt_id"]
    entries = [
        ("trial.ready", {"dashboard_revision": 0}),
        ("trial.started", {}),
        ("trial.commit_registered", {"dashboard_revision": 1}),
        ("trial.frozen", {"frozen_revision": 1, "last_rendered_revision": 1,
                           "reason": "deadline"}),
        ("trial.answering_ready", {"frozen_revision": 1}),
        ("control.stop", {}),
        ("trial.aborted", {"reason_code": "render_failed"}),
    ]
    for number, (name, metadata) in enumerate(entries, start=1):
        store.append_event(attempt_id, name, metadata, number)
    assert [row["event"] for row in store.list_events(attempt_id)] == [name for name, _ in entries]
    with pytest.raises(StudyStoreError, match="invalid_journal"):
        store.append_event(attempt_id, "trial.frozen", {"reason": "deadline", "free_text": "leak"}, 10)


def test_real_controller_and_store_share_internal_ids_and_journal(tmp_path):
    from backend.render_tracker import RenderTracker
    from backend.study import StudyController

    store = StudyStore(tmp_path)
    row = assignment()
    attempt_id = store.begin_attempt(row, "session-controller", consent(True), provenance())["attempt_id"]
    store.apply_event(attempt_id, "server:ready", "trial.ready", {})
    controller = StudyController(row, attempt_id, store, RenderTracker(), clock=lambda: 100)
    controller.handle_control({"type": "trial.start", "client_event_id": "client-start"}, 100)
    controller.record_request("request-1", "show a comparison", 101)
    assert [item["event"] for item in store.list_events(attempt_id)] == [
        "trial.started", "request.accepted"
    ]
    assert store.list_events(attempt_id)[1]["metadata"]["transcript"] == "show a comparison"


def test_restart_aborts_unexposed_attempt_but_never_retries_after_exposure(tmp_path):
    store = StudyStore(tmp_path)
    first = store.begin_attempt(assignment(), "session-1", consent(), provenance())["attempt_id"]
    second = store.begin_attempt(assignment(), "session-2", consent(), provenance())["attempt_id"]
    assert first != second
    assert store.get_attempt(first)["phase"] == "aborted"
    event(store, second, 1, "trial.ready")
    event(store, second, 2, "trial.start")
    assert store.get_attempt(second)["task_exposed"] is True
    with pytest.raises(StudyStoreError, match="task_already_exposed"):
        store.begin_attempt(assignment(), "session-3", consent(), provenance())


def test_pre_start_abort_remains_eligible_for_replacement(tmp_path):
    store = StudyStore(tmp_path)
    first = store.begin_attempt(assignment(), "session-1", consent(), provenance())["attempt_id"]
    event(store, first, 1, "trial.abort", {"reason_code": "startup_failed"})

    replacement = store.begin_attempt(
        assignment(), "session-2", consent(), provenance())

    assert replacement["attempt_id"] != first
    assert store.get_attempt(first)["task_exposed"] is False


def test_completed_assignment_can_never_start_again(tmp_path):
    store = StudyStore(tmp_path)
    attempt_id = start_and_freeze_ready(store)
    store.apply_event(attempt_id, "submit", "answer.submit", answer_payload())
    with pytest.raises(StudyStoreError, match="task_already_exposed"):
        store.begin_attempt(assignment(), "new-session", consent(), provenance())


def test_enqueue_is_memory_only_and_snapshot_is_strictly_bounded(tmp_path, monkeypatch):
    store = StudyStore(tmp_path)
    attempt_id = store.begin_attempt(assignment(), "session-1", consent(), provenance())["attempt_id"]
    original_connect = store._connect
    monkeypatch.setattr(store, "_connect", lambda: (_ for _ in ()).throw(AssertionError("disk I/O")))
    job = store.enqueue_evidence(attempt_id, {
        "dashboard_revision": 1, "dataset_id": "olist", "dataset_version": "v1",
        "views": [{"id": "v1", "view_revision": 1, "data": [{"x": 1}]}], "filters": [],
    }, {"reason": "commit"})
    assert job.startswith("evidence-")
    monkeypatch.setattr(store, "_connect", original_connect)
    assert store.get_evidence_status(attempt_id)["bytes_used"] > 0
    assert store.get_evidence_status(attempt_id)["pending_jobs"] == 1
    asyncio.run(store.flush_evidence(attempt_id))
    assert store.evidence_ready(attempt_id, 1)

    for snapshot in [
        {"dashboard_revision": 2, "views": [], "free_text": "leak"},
        {"dashboard_revision": 2, "views": [{"id": "v", "view_revision": 1,
                                               "metadata": {"credentials": "secret"}}]},
        {"dashboard_revision": 2, "views": [{"id": "v", "view_revision": 1,
                                               "source": {"tool": "aggregate", "path": "../secret"}}]},
        {"dashboard_revision": 2, "views": [{"id": "v", "view_revision": 1,
                                               "data": "not-a-row-list"}]},
    ]:
        with pytest.raises(StudyStoreError, match="invalid_evidence"):
            store.enqueue_evidence(attempt_id, snapshot, {})


def test_strict_payloads_ready_gate_drafts_and_questionnaire(tmp_path):
    store = StudyStore(tmp_path)
    attempt_id = store.begin_attempt(assignment(), "session-1", consent(), provenance())["attempt_id"]
    event(store, attempt_id, 1, "trial.ready")
    event(store, attempt_id, 2, "trial.start")
    event(store, attempt_id, 3, "trial.freeze", {
        "reason": "deadline", "frozen_revision": 0, "last_rendered_revision": None,
    })
    with pytest.raises(StudyStoreError, match="freeze_not_ready"):
        store.apply_event(attempt_id, "save-early", "answer.save", {
            "draft_version": 1, "conclusion": "x", "evidence_refs": [], "limitations": ""
        })
    event(store, attempt_id, 4, "trial.answering")
    saved = store.apply_event(attempt_id, "save-1", "answer.save", {
        "draft_version": 1, "conclusion": "x", "evidence_refs": [], "limitations": ""
    })
    assert saved["draft_version"] == 1
    with pytest.raises(StudyStoreError, match="draft_version"):
        store.apply_event(attempt_id, "save-2", "answer.save", {
            "draft_version": 1, "conclusion": "y", "evidence_refs": [], "limitations": ""
        })
    store.apply_event(attempt_id, "timeout", "answer.timeout", {})
    receipt = store.apply_event(attempt_id, "questionnaire", "questionnaire.submit", {
        "responses": {"continuity": 7, "control": 6, "effort": 2, "waiting_interference": 1}
    })
    assert receipt["questionnaire_status"] == "saved"
    with pytest.raises(StudyStoreError, match="payload"):
        store.apply_event(attempt_id, "bad-questionnaire", "questionnaire.submit", {
            "responses": {"continuity": 8, "control": 6, "effort": 2, "waiting_interference": 1}
        })
