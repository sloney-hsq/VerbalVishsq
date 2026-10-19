import asyncio
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from backend.study_store import StudyStore
from scripts.export_study import export_study
from test_study_store import answer_payload, assignment, consent, event, provenance


ROOT = Path(__file__).resolve().parents[1]


def completed_store(root, *, transcript=False):
    store = StudyStore(root)
    attempt_id = store.begin_attempt(assignment(), "session-1", consent(transcript), provenance())["attempt_id"]
    event(store, attempt_id, 1, "trial.ready")
    event(store, attempt_id, 2, "trial.start")
    event(store, attempt_id, 3, "trial.task_presented")
    store.append_event(attempt_id, "request.accepted", {
        "request_id": "r1", "classification": "analytical_request", "transcript": "private request"
    }, 100)
    evidence_id = store.enqueue_evidence(attempt_id, {
        "dashboard_revision": 1, "dataset_id": "olist", "dataset_version": "v1",
        "views": [{"id": "v1", "view_revision": 1, "data": [{"x": 1}]}], "filters": [],
    }, {"reason": "freeze", "renderer_version": "v1"})
    asyncio.run(store.flush_evidence(attempt_id))
    event(store, attempt_id, 4, "trial.freeze", {
        "reason": "deadline", "frozen_revision": 1, "last_rendered_revision": 1,
    })
    event(store, attempt_id, 5, "trial.answering")
    store.apply_event(attempt_id, "submit", "answer.submit",
                      answer_payload(evidence_refs=[{"revision": 1, "artifact_id": evidence_id}]))
    store.apply_event(attempt_id, "questionnaire", "questionnaire.submit", {
        "responses": {"continuity": 7, "control": 6, "effort": 2, "waiting_interference": 1}
    })
    return store, attempt_id


def test_blinded_ratings_export_has_only_answer_task_and_ready_evidence(tmp_path):
    _, _ = completed_store(tmp_path / "study", transcript=True)
    result = export_study(tmp_path / "study", tmp_path / "ratings", package="ratings")
    payload = json.loads((tmp_path / "ratings" / "ratings.json").read_text(encoding="utf-8"))
    text = json.dumps(payload)
    assert result["record_count"] == 1
    assert payload["records"][0]["task_id"] == "review-delivery-association"
    assert payload["records"][0]["answer_status"] == "submitted"
    assert (tmp_path / "ratings" / "artifacts").is_dir()
    for forbidden in ["condition", "participant_id", "session_id", "transcript", "created_ns", "duration"]:
        assert forbidden not in text
    with pytest.raises(ValueError, match="exists"):
        export_study(tmp_path / "study", tmp_path / "ratings", package="ratings")


def test_process_requires_transcript_consent(tmp_path):
    completed_store(tmp_path / "without", transcript=False)
    completed_store(tmp_path / "with", transcript=True)
    export_study(tmp_path / "without", tmp_path / "process-without", package="process")
    export_study(tmp_path / "with", tmp_path / "process-with", package="process")
    without = (tmp_path / "process-without" / "process.json").read_text(encoding="utf-8")
    with_consent = (tmp_path / "process-with" / "process.json").read_text(encoding="utf-8")
    assert "private request" not in without
    assert "private request" in with_consent
    assert "study_events" not in with_consent and "client_events" not in with_consent


def test_unready_cross_attempt_or_escaping_evidence_ref_is_rejected(tmp_path):
    store, attempt_id = completed_store(tmp_path / "study")
    artifact = store.list_evidence()[0]
    with sqlite3.connect(store.db_path) as db:
        db.execute("UPDATE evidence_artifacts SET relative_path='../outside.json' WHERE artifact_id=?",
                   (artifact["artifact_id"],))
    with pytest.raises(ValueError, match="evidence"):
        export_study(tmp_path / "study", tmp_path / "bad-path", package="ratings")

    with sqlite3.connect(store.db_path) as db:
        db.execute("UPDATE evidence_artifacts SET relative_path=?,status='pending' WHERE artifact_id=?",
                   (artifact["relative_path"], artifact["artifact_id"]))
    with pytest.raises(ValueError, match="evidence"):
        export_study(tmp_path / "study", tmp_path / "unready", package="ratings")


def test_technical_export_is_whitelisted_and_package_is_validated(tmp_path):
    completed_store(tmp_path / "study")
    export_study(tmp_path / "study", tmp_path / "technical", package="technical")
    payload = json.loads((tmp_path / "technical" / "technical.json").read_text(encoding="utf-8"))
    assert payload["records"][0]["phase"] == "completed"
    assert "provenance" in payload["records"][0]
    serialized = json.dumps(payload)
    assert "private request" not in serialized
    assert "receipt_json" not in serialized and "metadata_json" not in serialized
    with pytest.raises(ValueError, match="package"):
        export_study(tmp_path / "study", tmp_path / "unknown", package="raw")


def test_export_script_runs_from_clean_repo_cwd(tmp_path):
    completed_store(tmp_path / "study")
    command = [sys.executable, "scripts/export_study.py", "--study-data", str(tmp_path / "study"),
               "--output", str(tmp_path / "cli-export"), "--package", "technical"]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "cli-export" / "technical.json").exists()


def test_export_rejects_missing_study_database_without_creating_it(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="study database"):
        export_study(missing, tmp_path / "export", package="technical")
    assert not missing.exists()
