"""Durable, privacy-bounded storage for the fixed voice-policy study."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid
import asyncio
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

from .conditions import CANONICAL_CONDITIONS


EVIDENCE_LIMIT_BYTES = 50 * 1024 * 1024
ANSWER_TEXT_LIMIT_CHARS = 8_000
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_TERMINAL = {"completed", "aborted"}
_ASSIGNMENT_FIELDS = {
    "assignment_id", "participant_id", "trial_id", "task_id", "condition",
    "dataset_id", "study_id", "study_version", "manifest_sha256", "is_practice",
}
_PROVENANCE_FIELDS = {
    "git_commit", "git_dirty", "model", "prompt_sha256", "tool_schema_sha256",
    "dataset_version", "initial_dashboard_sha256",
}
_JOURNAL_FIELDS = {
    "trial.ready": {"dashboard_revision"},
    "trial.started": set(),
    "trial.commit_registered": {"dashboard_revision"},
    "trial.frozen": {"frozen_revision", "last_rendered_revision", "reason"},
    "trial.answering_ready": {"frozen_revision"},
    "trial.aborted": {"reason_code"},
    "control.stop": set(),
    "request.accepted": {"request_id", "classification", "transcript"},
    "response.stopped": {"request_id", "reason_code"},
    "deadline.reached": {"reason_code", "dashboard_revision"},
    "render.status": {"render_token", "dashboard_revision", "status", "error_code"},
    "evidence.status": {"job_id", "dashboard_revision", "status", "error_code"},
    "persistence.failure": {"error_code"},
}


class StudyStoreError(ValueError):
    def __init__(self, code, message=None):
        self.code = code
        super().__init__(f"{code}: {message or code}")


def _canonical_bytes(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StudyStoreError("invalid_payload", "payload must be finite JSON") from exc


def _hash(value):
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _safe_token(value, field):
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise StudyStoreError("invalid_payload", f"{field} must be a safe token")
    return value


def _exact(payload, fields):
    if not isinstance(payload, dict) or set(payload) != set(fields):
        raise StudyStoreError("invalid_payload", f"payload fields must be {sorted(fields)}")


class StudyStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.artifact_root = (self.root / "artifacts").resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        if self.artifact_root.parent != self.root:
            raise StudyStoreError("unsafe_path")
        self.db_path = self.root / "study.sqlite3"
        self._lock = threading.RLock()
        self._queue = {}
        self._initialize()
        self._load_cache()

    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self):
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS attempts (
                    attempt_id TEXT PRIMARY KEY, assignment_id TEXT NOT NULL,
                    participant_id TEXT NOT NULL, trial_id TEXT NOT NULL, task_id TEXT NOT NULL,
                    condition TEXT NOT NULL, dataset_id TEXT NOT NULL, study_id TEXT NOT NULL,
                    study_version TEXT NOT NULL, manifest_sha256 TEXT NOT NULL,
                    is_practice INTEGER NOT NULL, session_id TEXT NOT NULL UNIQUE,
                    phase TEXT NOT NULL, status TEXT NOT NULL, task_exposed INTEGER NOT NULL DEFAULT 0,
                    freeze_status TEXT, frozen_revision INTEGER, last_rendered_revision INTEGER,
                    consent_json TEXT NOT NULL, provenance_json TEXT NOT NULL,
                    evidence_failure TEXT, created_ns INTEGER NOT NULL, updated_ns INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS study_events (
                    attempt_id TEXT NOT NULL, seq INTEGER NOT NULL, schema_version INTEGER NOT NULL,
                    session_id TEXT NOT NULL, event TEXT NOT NULL, metadata_json TEXT NOT NULL,
                    now_ns INTEGER NOT NULL, PRIMARY KEY(attempt_id, seq),
                    FOREIGN KEY(attempt_id) REFERENCES attempts(attempt_id)
                );
                CREATE TABLE IF NOT EXISTS client_events (
                    attempt_id TEXT NOT NULL, client_event_id TEXT NOT NULL,
                    event_type TEXT NOT NULL, payload_hash TEXT NOT NULL,
                    receipt_json TEXT NOT NULL, created_ns INTEGER NOT NULL,
                    PRIMARY KEY(attempt_id, client_event_id),
                    FOREIGN KEY(attempt_id) REFERENCES attempts(attempt_id)
                );
                CREATE TABLE IF NOT EXISTS answer_drafts (
                    attempt_id TEXT NOT NULL, draft_version INTEGER NOT NULL,
                    content_json TEXT NOT NULL, content_hash TEXT NOT NULL, created_ns INTEGER NOT NULL,
                    PRIMARY KEY(attempt_id, draft_version),
                    FOREIGN KEY(attempt_id) REFERENCES attempts(attempt_id)
                );
                CREATE TABLE IF NOT EXISTS answers (
                    answer_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL,
                    submission_id TEXT, answer_status TEXT NOT NULL, conclusion TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL, limitations TEXT NOT NULL,
                    content_hash TEXT NOT NULL, receipt_json TEXT NOT NULL, created_ns INTEGER NOT NULL,
                    UNIQUE(attempt_id, submission_id),
                    FOREIGN KEY(attempt_id) REFERENCES attempts(attempt_id)
                );
                CREATE TABLE IF NOT EXISTS questionnaires (
                    attempt_id TEXT PRIMARY KEY, responses_json TEXT NOT NULL, created_ns INTEGER NOT NULL,
                    FOREIGN KEY(attempt_id) REFERENCES attempts(attempt_id)
                );
                CREATE TABLE IF NOT EXISTS evidence_artifacts (
                    artifact_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    status TEXT NOT NULL, byte_count INTEGER NOT NULL, sha256 TEXT NOT NULL,
                    relative_path TEXT, provenance_json TEXT NOT NULL, error_code TEXT,
                    created_ns INTEGER NOT NULL, ready_ns INTEGER,
                    UNIQUE(attempt_id, revision),
                    FOREIGN KEY(attempt_id) REFERENCES attempts(attempt_id)
                );
            """)

    def _load_cache(self):
        self._attempt_cache = {}
        self._evidence_bytes = defaultdict(int)
        self._evidence_revisions = defaultdict(set)
        with self._connect() as db:
            for row in db.execute("SELECT attempt_id,phase,task_exposed,consent_json,evidence_failure FROM attempts"):
                self._attempt_cache[row["attempt_id"]] = {
                    "phase": row["phase"], "task_exposed": bool(row["task_exposed"]),
                    "consent": json.loads(row["consent_json"]),
                    "evidence_failure": row["evidence_failure"],
                }
            for row in db.execute("SELECT attempt_id,revision,byte_count,status FROM evidence_artifacts"):
                self._evidence_bytes[row["attempt_id"]] += row["byte_count"]
                self._evidence_revisions[row["attempt_id"]].add(row["revision"])

    def _assignment(self, assignment):
        if not isinstance(assignment, dict) or not _ASSIGNMENT_FIELDS.issubset(assignment):
            raise StudyStoreError("invalid_assignment")
        row = {field: assignment[field] for field in _ASSIGNMENT_FIELDS}
        for field in _ASSIGNMENT_FIELDS - {"is_practice", "condition", "manifest_sha256"}:
            _safe_token(row[field], field)
        if row["condition"] not in CANONICAL_CONDITIONS:
            raise StudyStoreError("invalid_assignment", "condition")
        if row["is_practice"] is not False:
            raise StudyStoreError("invalid_assignment", "formal assignment required")
        if not isinstance(row["manifest_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["manifest_sha256"]):
            raise StudyStoreError("invalid_assignment", "manifest hash")
        return row

    def _consent(self, consent):
        _exact(consent, {"transcript", "analysis_evidence", "final_answer"})
        if any(type(value) is not bool for value in consent.values()):
            raise StudyStoreError("invalid_consent")
        if not consent["analysis_evidence"] or not consent["final_answer"]:
            raise StudyStoreError("required_consent_missing")
        return dict(consent)

    def _provenance(self, provenance):
        _exact(provenance, _PROVENANCE_FIELDS)
        if type(provenance["git_dirty"]) is not bool:
            raise StudyStoreError("invalid_provenance", "git_dirty")
        for field in _PROVENANCE_FIELDS - {"git_dirty"}:
            if not isinstance(provenance[field], str) or not provenance[field]:
                raise StudyStoreError("invalid_provenance", field)
        return dict(provenance)

    def begin_attempt(self, assignment: dict, session_id: str,
                      consent: dict, provenance: dict) -> dict:
        assignment = self._assignment(assignment)
        session_id = _safe_token(session_id, "session_id")
        consent = self._consent(consent)
        provenance = self._provenance(provenance)
        attempt_id = f"attempt-{uuid.uuid4().hex}"
        now = time.time_ns()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                history = db.execute(
                    "SELECT attempt_id,task_exposed,phase FROM attempts WHERE assignment_id=?",
                    (assignment["assignment_id"],),
                ).fetchall()
                if any(row["task_exposed"] or row["phase"] == "completed" for row in history):
                    raise StudyStoreError("task_already_exposed")
                prior = [row for row in history if row["phase"] not in _TERMINAL]
                for row in prior:
                    db.execute("UPDATE attempts SET phase='aborted', status='restart', updated_ns=? WHERE attempt_id=?",
                               (now, row["attempt_id"]))
                db.execute("""
                    INSERT INTO attempts (
                        attempt_id,assignment_id,participant_id,trial_id,task_id,condition,dataset_id,
                        study_id,study_version,manifest_sha256,is_practice,session_id,phase,status,
                        consent_json,provenance_json,created_ns,updated_ns
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    attempt_id, assignment["assignment_id"], assignment["participant_id"],
                    assignment["trial_id"], assignment["task_id"], assignment["condition"],
                    assignment["dataset_id"], assignment["study_id"], assignment["study_version"],
                    assignment["manifest_sha256"], 0, session_id, "preparing", "active",
                    json.dumps(consent, sort_keys=True), json.dumps(provenance, sort_keys=True), now, now,
                ))
                db.commit()
                for row in prior:
                    self._attempt_cache[row["attempt_id"]]["phase"] = "aborted"
                self._attempt_cache[attempt_id] = {
                    "phase": "preparing", "task_exposed": False, "consent": dict(consent),
                    "evidence_failure": None,
                }
            except Exception:
                db.rollback()
                raise
        return {"attempt_id": attempt_id, "phase": "preparing", "session_id": session_id,
                "assignment_id": assignment["assignment_id"]}

    def _attempt_row(self, db, attempt_id):
        _safe_token(attempt_id, "attempt_id")
        row = db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        if row is None:
            raise StudyStoreError("unknown_attempt")
        return row

    def _answer_content(self, payload, *, submit):
        fields = {"conclusion", "evidence_refs", "limitations"}
        if submit:
            fields.add("submission_id")
        else:
            fields.add("draft_version")
        _exact(payload, fields)
        conclusion, limitations = payload["conclusion"], payload["limitations"]
        if not isinstance(conclusion, str) or not isinstance(limitations, str):
            raise StudyStoreError("invalid_payload", "answer text")
        if len(conclusion) + len(limitations) > ANSWER_TEXT_LIMIT_CHARS:
            raise StudyStoreError("answer_text_limit")
        refs = payload["evidence_refs"]
        if not isinstance(refs, list) or len(refs) > 100:
            raise StudyStoreError("invalid_payload", "evidence_refs")
        clean_refs = []
        for ref in refs:
            _exact(ref, {"revision", "artifact_id"})
            if type(ref["revision"]) is not int or ref["revision"] < 0:
                raise StudyStoreError("invalid_payload", "revision")
            clean_refs.append({"revision": ref["revision"],
                               "artifact_id": _safe_token(ref["artifact_id"], "artifact_id")})
        result = {"conclusion": conclusion, "evidence_refs": clean_refs, "limitations": limitations}
        if submit:
            result["submission_id"] = _safe_token(payload["submission_id"], "submission_id")
        else:
            if type(payload["draft_version"]) is not int or payload["draft_version"] < 1:
                raise StudyStoreError("invalid_payload", "draft_version")
            result["draft_version"] = payload["draft_version"]
        return result

    def _validate_refs(self, db, attempt_id, refs):
        for ref in refs:
            row = db.execute(
                "SELECT 1 FROM evidence_artifacts WHERE artifact_id=? AND attempt_id=? AND revision=? AND status='ready'",
                (ref["artifact_id"], attempt_id, ref["revision"]),
            ).fetchone()
            if row is None:
                raise StudyStoreError("evidence_not_ready")

    def _receipt(self, attempt_id, client_event_id, event_type, phase, status="accepted", **extra):
        return {"attempt_id": attempt_id, "client_event_id": client_event_id,
                "event_type": event_type, "phase": phase, "status": status, **extra}

    def apply_event(self, attempt_id: str, client_event_id: str,
                    event_type: str, payload: dict) -> dict:
        attempt_id = _safe_token(attempt_id, "attempt_id")
        client_event_id = _safe_token(client_event_id, "client_event_id")
        if not isinstance(event_type, str) or event_type not in {
            "trial.ready", "trial.start", "trial.task_presented", "trial.freeze",
            "trial.answering", "answer.save", "answer.submit", "answer.timeout",
            "questionnaire.submit", "trial.abort",
        }:
            raise StudyStoreError("unknown_event_type")
        if not isinstance(payload, dict):
            raise StudyStoreError("invalid_payload")
        event_hash = _hash({"event_type": event_type, "payload": payload})
        now = time.time_ns()
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                attempt = self._attempt_row(db, attempt_id)
                old = db.execute(
                    "SELECT payload_hash,receipt_json FROM client_events WHERE attempt_id=? AND client_event_id=?",
                    (attempt_id, client_event_id),
                ).fetchone()
                if old:
                    if old["payload_hash"] != event_hash:
                        raise StudyStoreError("idempotency_conflict")
                    db.rollback()
                    return json.loads(old["receipt_json"])

                # submission_id is a second, business-level idempotency key.
                if event_type == "answer.submit":
                    content = self._answer_content(payload, submit=True)
                    existing = db.execute(
                        "SELECT content_hash,receipt_json FROM answers WHERE attempt_id=? AND submission_id=?",
                        (attempt_id, content["submission_id"]),
                    ).fetchone()
                    if existing:
                        content_hash = _hash(content)
                        if existing["content_hash"] != content_hash:
                            raise StudyStoreError("submission_conflict")
                        receipt = json.loads(existing["receipt_json"])
                        db.execute("INSERT INTO client_events VALUES (?,?,?,?,?,?)",
                                   (attempt_id, client_event_id, event_type, event_hash,
                                    json.dumps(receipt, sort_keys=True), now))
                        db.commit()
                        return receipt

                phase, freeze_status = attempt["phase"], attempt["freeze_status"]
                if phase in _TERMINAL and event_type != "questionnaire.submit":
                    raise StudyStoreError("terminal_state")
                status = "accepted"
                extra = {}
                if event_type == "trial.ready":
                    _exact(payload, set())
                    if phase != "preparing": raise StudyStoreError("invalid_transition")
                    phase = "ready"
                elif event_type == "trial.start":
                    _exact(payload, set())
                    if phase != "ready": raise StudyStoreError("invalid_transition")
                    phase = "exploring"
                    # Accepting start is the server-side disclosure boundary: the
                    # task is included in the resulting exploring state, so retry
                    # protection cannot depend on a later best-effort browser ACK.
                    db.execute("UPDATE attempts SET task_exposed=1 WHERE attempt_id=?", (attempt_id,))
                elif event_type == "trial.task_presented":
                    _exact(payload, set())
                    if phase != "exploring": raise StudyStoreError("invalid_transition")
                    db.execute("UPDATE attempts SET task_exposed=1 WHERE attempt_id=?", (attempt_id,))
                elif event_type == "trial.freeze":
                    _exact(payload, {"reason", "frozen_revision", "last_rendered_revision"})
                    _safe_token(payload["reason"], "reason")
                    if (phase != "exploring" or type(payload["frozen_revision"]) is not int or
                            payload["frozen_revision"] < 0 or
                            (payload["last_rendered_revision"] is not None and
                             (type(payload["last_rendered_revision"]) is not int or
                              payload["last_rendered_revision"] < 0))):
                        raise StudyStoreError("invalid_transition")
                    phase, freeze_status = "answering", "pending"
                    db.execute("UPDATE attempts SET frozen_revision=?,last_rendered_revision=? WHERE attempt_id=?",
                               (payload["frozen_revision"], payload["last_rendered_revision"], attempt_id))
                elif event_type == "trial.answering":
                    _exact(payload, set())
                    if phase != "answering" or freeze_status != "pending":
                        raise StudyStoreError("invalid_transition")
                    freeze_status = "ready"
                elif event_type == "answer.save":
                    if phase != "answering" or freeze_status != "ready":
                        raise StudyStoreError("freeze_not_ready")
                    content = self._answer_content(payload, submit=False)
                    self._validate_refs(db, attempt_id, content["evidence_refs"])
                    latest = db.execute("SELECT MAX(draft_version) AS version FROM answer_drafts WHERE attempt_id=?",
                                        (attempt_id,)).fetchone()["version"]
                    if latest is not None and content["draft_version"] <= latest:
                        raise StudyStoreError("draft_version_conflict")
                    db.execute("INSERT INTO answer_drafts VALUES (?,?,?,?,?)",
                               (attempt_id, content["draft_version"], json.dumps(content, sort_keys=True),
                                _hash(content), now))
                    status, extra = "saved", {"draft_version": content["draft_version"]}
                elif event_type == "answer.submit":
                    if phase != "answering" or freeze_status != "ready":
                        raise StudyStoreError("freeze_not_ready")
                    content = self._answer_content(payload, submit=True)
                    self._validate_refs(db, attempt_id, content["evidence_refs"])
                    phase, status = "completed", "saved"
                    extra = {"answer_status": "submitted"}
                    receipt = self._receipt(attempt_id, client_event_id, event_type, phase, status, **extra)
                    db.execute("INSERT INTO answers VALUES (?,?,?,?,?,?,?,?,?,?)", (
                        f"answer-{uuid.uuid4().hex}", attempt_id, content["submission_id"], "submitted",
                        content["conclusion"], json.dumps(content["evidence_refs"], sort_keys=True),
                        content["limitations"], _hash(content), json.dumps(receipt, sort_keys=True), now,
                    ))
                elif event_type == "answer.timeout":
                    _exact(payload, set())
                    if phase != "answering" or freeze_status != "ready":
                        raise StudyStoreError("freeze_not_ready")
                    draft = db.execute(
                        "SELECT content_json FROM answer_drafts WHERE attempt_id=? ORDER BY draft_version DESC LIMIT 1",
                        (attempt_id,),
                    ).fetchone()
                    content = json.loads(draft["content_json"]) if draft else {
                        "conclusion": "", "limitations": "", "evidence_refs": []}
                    answer_status = "partial" if (content["conclusion"] or content["limitations"] or
                                                  content["evidence_refs"]) else "empty"
                    phase, status, extra = "completed", "saved", {"answer_status": answer_status}
                    receipt = self._receipt(attempt_id, client_event_id, event_type, phase, status, **extra)
                    db.execute("INSERT INTO answers VALUES (?,?,?,?,?,?,?,?,?,?)", (
                        f"answer-{uuid.uuid4().hex}", attempt_id, None, answer_status,
                        content["conclusion"], json.dumps(content["evidence_refs"], sort_keys=True),
                        content["limitations"], _hash(content), json.dumps(receipt, sort_keys=True), now,
                    ))
                elif event_type == "questionnaire.submit":
                    _exact(payload, {"responses"})
                    if phase != "completed": raise StudyStoreError("invalid_transition")
                    responses = payload["responses"]
                    fields = {"continuity", "control", "effort", "waiting_interference"}
                    _exact(responses, fields)
                    if any(type(value) is not int or not 1 <= value <= 7 for value in responses.values()):
                        raise StudyStoreError("invalid_payload", "questionnaire")
                    if db.execute("SELECT 1 FROM questionnaires WHERE attempt_id=?", (attempt_id,)).fetchone():
                        raise StudyStoreError("questionnaire_conflict")
                    db.execute("INSERT INTO questionnaires VALUES (?,?,?)",
                               (attempt_id, json.dumps(responses, sort_keys=True), now))
                    status, extra = "saved", {"questionnaire_status": "saved"}
                elif event_type == "trial.abort":
                    _exact(payload, {"reason_code"})
                    _safe_token(payload["reason_code"], "reason_code")
                    phase, status = "aborted", payload["reason_code"]

                receipt = self._receipt(attempt_id, client_event_id, event_type, phase, status, **extra)
                db.execute("UPDATE attempts SET phase=?,status=?,freeze_status=?,updated_ns=? WHERE attempt_id=?",
                           (phase, status, freeze_status, now, attempt_id))
                db.execute("INSERT INTO client_events VALUES (?,?,?,?,?,?)",
                           (attempt_id, client_event_id, event_type, event_hash,
                            json.dumps(receipt, sort_keys=True), now))
                db.commit()
                cached = self._attempt_cache[attempt_id]
                cached["phase"] = phase
                if event_type in {"trial.start", "trial.task_presented"}:
                    cached["task_exposed"] = True
                return receipt
            except Exception:
                db.rollback()
                raise

    def append_event(self, attempt_id: str, event: str, metadata: dict, now_ns: int) -> None:
        if event not in _JOURNAL_FIELDS or not isinstance(metadata, dict):
            raise StudyStoreError("invalid_journal_event")
        if type(now_ns) is not int or now_ns < 0:
            raise StudyStoreError("invalid_journal_event", "now_ns")
        allowed = _JOURNAL_FIELDS[event]
        if not set(metadata).issubset(allowed):
            raise StudyStoreError("invalid_journal_metadata")
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                attempt = self._attempt_row(db, attempt_id)
                clean = {}
                consent = json.loads(attempt["consent_json"])
                for key, value in metadata.items():
                    if key == "transcript" and not consent["transcript"]:
                        continue
                    if key == "transcript":
                        if not isinstance(value, str) or len(value) > 8_000:
                            raise StudyStoreError("invalid_journal_metadata", "transcript")
                    elif not (value is None or type(value) in {str, int, bool}):
                        raise StudyStoreError("invalid_journal_metadata")
                    clean[key] = value
                next_seq = db.execute(
                    "SELECT COALESCE(MAX(seq),0)+1 AS seq FROM study_events WHERE attempt_id=?",
                    (attempt_id,),
                ).fetchone()["seq"]
                db.execute("INSERT INTO study_events VALUES (?,?,?,?,?,?,?)", (
                    attempt_id, next_seq, 1, attempt["session_id"], event,
                    json.dumps(clean, ensure_ascii=False, sort_keys=True), now_ns,
                ))
                db.commit()
            except Exception:
                db.rollback()
                raise

    def _evidence_snapshot(self, snapshot):
        if not isinstance(snapshot, dict) or type(snapshot.get("dashboard_revision")) is not int or snapshot["dashboard_revision"] < 0:
            raise StudyStoreError("invalid_evidence", "dashboard_revision")
        root_fields = {"views", "filters", "highlighted", "highlight_element", "dim_others",
                       "active_view_id", "dashboard_revision", "dataset_id", "dataset_version"}
        if not set(snapshot).issubset(root_fields) or not isinstance(snapshot.get("views"), list):
            raise StudyStoreError("invalid_evidence", "dashboard fields")
        view_fields = {
            "id", "highlighted", "view_revision", "scope_mode", "scope_filters",
            "selection_filters", "selection_highlights", "chart_type", "x_field", "y_field",
            "color", "title", "source", "visual", "data", "columns", "truncated",
            "result_kind", "metadata",
        }
        for view in snapshot["views"]:
            if (not isinstance(view, dict) or not set(view).issubset(view_fields) or
                    not isinstance(view.get("id"), str) or
                    type(view.get("view_revision")) is not int or view["view_revision"] < 0):
                raise StudyStoreError("invalid_evidence", "view fields")
            if "data" in view and (not isinstance(view["data"], list) or
                                   any(not isinstance(row, dict) for row in view["data"])):
                raise StudyStoreError("invalid_evidence", "view data")
            if "columns" in view and not isinstance(view["columns"], dict):
                raise StudyStoreError("invalid_evidence", "view columns")
            if "source" in view and (not isinstance(view["source"], dict) or
                                     not set(view["source"]).issubset({"tool", "arguments"})):
                raise StudyStoreError("invalid_evidence", "source fields")

        sensitive = {"transcript", "audio", "raw_audio", "credentials", "credential",
                     "secret", "api_key", "password", "path", "file_path"}
        def inspect(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if not isinstance(key, str) or key.lower() in sensitive:
                        raise StudyStoreError("invalid_evidence", "sensitive nested field")
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)
        inspect(snapshot)
        return _canonical_bytes(deepcopy(snapshot))

    def enqueue_evidence(self, attempt_id: str, snapshot: dict, provenance: dict) -> str:
        attempt_id = _safe_token(attempt_id, "attempt_id")
        encoded = self._evidence_snapshot(snapshot)
        if not isinstance(provenance, dict) or any(not isinstance(key, str) for key in provenance):
            raise StudyStoreError("invalid_evidence", "provenance")
        if any(key not in {"renderer_version", "reason", "captured_ns"} for key in provenance):
            raise StudyStoreError("invalid_evidence", "provenance field")
        job_id = f"evidence-{uuid.uuid4().hex}"
        revision = snapshot["dashboard_revision"]
        with self._lock:
            attempt = self._attempt_cache.get(attempt_id)
            if attempt is None:
                raise StudyStoreError("unknown_attempt")
            if attempt["phase"] in _TERMINAL or attempt["evidence_failure"]:
                raise StudyStoreError("evidence_unavailable")
            if not attempt["consent"]["analysis_evidence"]:
                raise StudyStoreError("evidence_consent_required")
            if self._evidence_bytes[attempt_id] + len(encoded) > EVIDENCE_LIMIT_BYTES:
                raise StudyStoreError("evidence_limit")
            if revision in self._evidence_revisions[attempt_id]:
                raise StudyStoreError("evidence_revision_conflict")
            self._evidence_bytes[attempt_id] += len(encoded)
            self._evidence_revisions[attempt_id].add(revision)
            self._queue[job_id] = {
                "attempt_id": attempt_id, "revision": revision, "encoded": encoded,
                "provenance": deepcopy(provenance), "created_ns": time.time_ns(),
                "state": "queued",
            }
        return job_id

    async def flush_evidence(self, attempt_id: str) -> None:
        _safe_token(attempt_id, "attempt_id")
        with self._lock:
            jobs = []
            for job_id, job in self._queue.items():
                if job["attempt_id"] == attempt_id and job["state"] == "queued":
                    job["state"] = "flushing"
                    jobs.append((job_id, dict(job)))
        for job_id, job in jobs:
            await asyncio.to_thread(self._flush_evidence_job, job_id, job)

    def _flush_evidence_job(self, job_id, job):
            attempt_id = job["attempt_id"]
            encoded = job["encoded"]
            directory = (self.artifact_root / attempt_id).resolve()
            if directory.parent != self.artifact_root:
                raise StudyStoreError("unsafe_path")
            directory.mkdir(parents=True, exist_ok=True)
            final = (directory / f"{job_id}.json").resolve()
            temporary = (directory / f".{job_id}.{uuid.uuid4().hex}.tmp").resolve()
            if final.parent != directory or temporary.parent != directory:
                raise StudyStoreError("unsafe_path")
            try:
                with open(temporary, "xb") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, final)
                relative = final.relative_to(self.root).as_posix()
                with self._lock, self._connect() as db:
                    db.execute("INSERT INTO evidence_artifacts VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                        job_id, attempt_id, job["revision"], "ready", len(encoded),
                        hashlib.sha256(encoded).hexdigest(), relative,
                        json.dumps(job["provenance"], sort_keys=True), None,
                        job["created_ns"], time.time_ns(),
                    ))
                    self._queue.pop(job_id, None)
            except Exception:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
                with self._lock, self._connect() as db:
                    db.execute("INSERT OR REPLACE INTO evidence_artifacts VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                        job_id, attempt_id, job["revision"], "failed", len(encoded),
                        hashlib.sha256(encoded).hexdigest(), None,
                        json.dumps(job["provenance"], sort_keys=True), "write_failed",
                        job["created_ns"], None,
                    ))
                    db.execute("UPDATE attempts SET evidence_failure='write_failed',updated_ns=? WHERE attempt_id=?",
                               (time.time_ns(), attempt_id))
                    self._queue.pop(job_id, None)
                    self._attempt_cache[attempt_id]["evidence_failure"] = "write_failed"

    def evidence_ready(self, attempt_id: str, revision: int) -> bool:
        if type(revision) is not int or revision < 0:
            return False
        with self._connect() as db:
            self._attempt_row(db, attempt_id)
            return db.execute(
                "SELECT 1 FROM evidence_artifacts WHERE attempt_id=? AND revision=? AND status='ready'",
                (attempt_id, revision),
            ).fetchone() is not None

    def get_evidence_status(self, attempt_id: str) -> dict:
        with self._connect() as db:
            attempt = self._attempt_row(db, attempt_id)
            rows = db.execute("SELECT status,revision,byte_count FROM evidence_artifacts WHERE attempt_id=?",
                              (attempt_id,)).fetchall()
        with self._lock:
            pending = sum(job["attempt_id"] == attempt_id for job in self._queue.values())
        return {
            "ready_revisions": sorted(row["revision"] for row in rows if row["status"] == "ready"),
            "pending_jobs": pending + sum(row["status"] == "pending" for row in rows),
            "failed_jobs": sum(row["status"] == "failed" for row in rows),
            "bytes_used": self._evidence_bytes[attempt_id],
            "limit_bytes": EVIDENCE_LIMIT_BYTES,
            "error_code": attempt["evidence_failure"],
        }

    def get_evidence_refs(self, attempt_id: str) -> list[dict]:
        with self._connect() as db:
            self._attempt_row(db, attempt_id)
            rows = db.execute(
                "SELECT artifact_id,revision FROM evidence_artifacts WHERE attempt_id=? AND status='ready' ORDER BY revision",
                (attempt_id,),
            ).fetchall()
        return [{"revision": row["revision"], "artifact_id": row["artifact_id"]} for row in rows]

    def recover_incomplete(self) -> list[str]:
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT attempt_id FROM attempts WHERE phase NOT IN ('completed','aborted') ORDER BY created_ns").fetchall()
            attempt_ids = [row["attempt_id"] for row in rows]
            if attempt_ids:
                db.execute("BEGIN IMMEDIATE")
                now = time.time_ns()
                for attempt_id in attempt_ids:
                    db.execute("UPDATE attempts SET phase='aborted',status='process_restart',updated_ns=? WHERE attempt_id=?",
                               (now, attempt_id))
                db.commit()
                for attempt_id in attempt_ids:
                    self._attempt_cache[attempt_id]["phase"] = "aborted"
            return attempt_ids

    def get_attempt(self, attempt_id: str) -> dict:
        with self._connect() as db:
            row = self._attempt_row(db, attempt_id)
            result = dict(row)
            answer = db.execute(
                "SELECT answer_status FROM answers WHERE attempt_id=? ORDER BY created_ns DESC LIMIT 1",
                (attempt_id,),
            ).fetchone()
        result["is_practice"] = bool(result["is_practice"])
        result["task_exposed"] = bool(result["task_exposed"])
        result["consent"] = json.loads(result.pop("consent_json"))
        result["provenance"] = json.loads(result.pop("provenance_json"))
        result["answer_status"] = answer["answer_status"] if answer else None
        return result

    def list_attempts(self) -> list[dict]:
        with self._connect() as db:
            ids = [row["attempt_id"] for row in db.execute("SELECT attempt_id FROM attempts ORDER BY created_ns")]
        return [self.get_attempt(attempt_id) for attempt_id in ids]

    def list_events(self, attempt_id=None) -> list[dict]:
        with self._connect() as db:
            if attempt_id is None:
                rows = db.execute("SELECT * FROM study_events ORDER BY attempt_id,seq").fetchall()
            else:
                self._attempt_row(db, attempt_id)
                rows = db.execute("SELECT * FROM study_events WHERE attempt_id=? ORDER BY seq", (attempt_id,)).fetchall()
        return [{**dict(row), "metadata": json.loads(row["metadata_json"])} for row in rows]

    def list_answers(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM answers ORDER BY created_ns").fetchall()
        return [{**dict(row), "evidence_refs": json.loads(row["evidence_refs_json"])} for row in rows]

    def list_questionnaires(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM questionnaires ORDER BY created_ns").fetchall()
        return [{"attempt_id": row["attempt_id"], "responses": json.loads(row["responses_json"]),
                 "created_ns": row["created_ns"]} for row in rows]

    def list_evidence(self) -> list[dict]:
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM evidence_artifacts ORDER BY created_ns")]
