"""Server-authoritative lifecycle for one formal between-subject study trial."""
from copy import deepcopy
import re
from time import monotonic_ns
from uuid import uuid4

from .study_store import StudyStoreError


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_IDENTITY_FIELDS = {
    "assignment_id", "attempt_id", "condition", "participant_id", "trial_id",
    "task_id", "session_id", "dataset_id", "study_id", "study_version",
    "manifest_sha256", "snapshot", "path", "file_path",
}
_EFFECTS = {"input", "commit", "analysis_output"}


class StudyError(ValueError):
    def __init__(self, code, message=None, *, state=None):
        self.code = code
        self.state = deepcopy(state) if state is not None else None
        super().__init__(message or code.replace("_", " "))


class StudyController:
    """Owns timing and study gates; ResponseProtocol still owns response authority."""

    exploration_limit_ns = 600 * 1_000_000_000
    answer_limit_ns = 180 * 1_000_000_000
    readiness_limit_ns = 15 * 1_000_000_000

    def __init__(self, assignment: dict, attempt_id: str, store, render_tracker, clock=monotonic_ns):
        required = {
            "assignment_id", "participant_id", "trial_id", "task_id", "condition",
            "dataset_id", "study_id", "study_version", "manifest_sha256", "is_practice",
        }
        if not isinstance(assignment, dict) or not required.issubset(assignment):
            raise StudyError("invalid_assignment")
        if assignment.get("condition") not in {"revision_enabled", "turn_taking"}:
            raise StudyError("invalid_assignment")
        if not isinstance(attempt_id, str) or not _SAFE_ID.fullmatch(attempt_id):
            raise StudyError("invalid_attempt_id")
        self.assignment = deepcopy(assignment)
        self.attempt_id = attempt_id
        self.store = store
        self.render_tracker = render_tracker
        self.clock = clock
        attempt = store.get_attempt(attempt_id)
        self.phase = attempt.get("phase", "preparing")
        self.freeze_status = attempt.get("freeze_status")
        self.answer_status = attempt.get("answer_status")
        self.exploration_deadline_ns = None
        self.answer_deadline_ns = None
        self._gate_open = False
        self._expired = False
        self._frozen = None
        self._frozen_render = None
        self._readiness_deadline_ns = None
        self._startup_render = None
        self._startup_deadline_ns = None
        self._enqueued_revisions = set()
        self._last_rendered_revision = None
        self._client_results = {}
        self.renderer_version = None

    def check_effect(self, kind: str, now_ns: int) -> bool:
        if kind not in _EFFECTS:
            raise StudyError("invalid_effect_kind")
        return bool(self.phase == "exploring" and self._gate_open and
                    self.exploration_deadline_ns is not None and
                    now_ns < self.exploration_deadline_ns)

    def expire_if_due(self, now_ns: int) -> bool:
        if (self.phase == "exploring" and self._gate_open and
                self.exploration_deadline_ns is not None and
                now_ns >= self.exploration_deadline_ns):
            self._gate_open = False
            self._expired = True
            return True
        return False

    def provider_ready(self, snapshot: dict, now_ns: int) -> dict:
        if self.phase != "preparing":
            raise StudyError("invalid_phase")
        snap = self._snapshot(snapshot)
        try:
            render = self.render_tracker.register(self.attempt_id, snap, "init")
            self._enqueue_evidence(snap, now_ns, "init")
        except Exception as error:
            self._abort("startup_failed", now_ns)
            raise StudyError("startup_failed") from error
        self._startup_render = render
        self._startup_deadline_ns = now_ns + self.readiness_limit_ns
        return self.state(now_ns, render=render)

    def register_commit(self, snapshot: dict, now_ns: int) -> dict:
        if not self.check_effect("commit", now_ns):
            raise StudyError("effect_not_allowed")
        snap = self._snapshot(snapshot)
        try:
            render = self.render_tracker.register(self.attempt_id, snap, "commit")
            self._enqueue_evidence(snap, now_ns, "commit")
        except Exception as error:
            self._gate_open = False
            self._abort("evidence_persist_failed", now_ns)
            raise StudyError("evidence_persist_failed") from error
        self._journal("trial.commit_registered", {"dashboard_revision": snap["dashboard_revision"]}, now_ns)
        return render

    def record_request(self, request_id: str, transcript: str, now_ns: int) -> None:
        if not self.check_effect("input", now_ns):
            raise StudyError("effect_not_allowed")
        if not isinstance(request_id, str) or not _SAFE_ID.fullmatch(request_id):
            raise StudyError("invalid_request_id")
        if not isinstance(transcript, str):
            raise StudyError("invalid_transcript")
        self._journal("request.accepted", {
            "request_id": request_id,
            "classification": "analytical_request",
            "transcript": transcript,
        }, now_ns)

    def freeze(self, snapshot: dict, last_rendered_revision: int | None,
               now_ns: int, reason: str) -> dict:
        if self._frozen is not None:
            return deepcopy(self._frozen)
        if self.phase != "exploring":
            raise StudyError("invalid_phase")
        snap = self._snapshot(snapshot)
        self._gate_open = False
        self._expired = True
        try:
            render = self.render_tracker.register(self.attempt_id, snap, "frozen")
            self._enqueue_evidence(snap, now_ns, "frozen")
            self._apply_internal("trial.freeze", {
                "reason": self._safe_reason(reason),
                "frozen_revision": snap["dashboard_revision"],
                "last_rendered_revision": last_rendered_revision,
            })
        except Exception as error:
            self._abort("evidence_persist_failed", now_ns)
            raise StudyError("evidence_persist_failed") from error
        self.phase = "answering"
        self.freeze_status = "pending"
        self._frozen_render = render
        self._last_rendered_revision = last_rendered_revision
        self._readiness_deadline_ns = now_ns + self.readiness_limit_ns
        self._journal("trial.frozen", {
            "frozen_revision": snap["dashboard_revision"],
            "last_rendered_revision": last_rendered_revision,
            "reason": self._safe_reason(reason),
        }, now_ns)
        self._frozen = {
            "type": "trial.frozen",
            "state": deepcopy(snap),
            "dashboard_revision": snap["dashboard_revision"],
            "frozen_committed_revision": snap["dashboard_revision"],
            "last_rendered_revision": last_rendered_revision,
            "render": deepcopy(render),
            "freeze_status": "pending",
        }
        return deepcopy(self._frozen)

    def handle_control(self, event: dict, now_ns: int) -> dict:
        kind, event_id, payload = self._validate_control(event)
        previous = self._client_results.get(event_id)
        if previous is not None:
            if previous[0] != kind or previous[1] != payload:
                raise StudyError("idempotency_conflict")
            return {"receipt": deepcopy(previous[2]), "state": self.state(now_ns)}
        if kind == "trial.start":
            if self.phase != "ready":
                raise StudyError("invalid_phase")
            receipt = self.store.apply_event(self.attempt_id, event_id, kind, payload)
            self.phase = "exploring"
            self._gate_open = True
            self._expired = False
            self.exploration_deadline_ns = now_ns + self.exploration_limit_ns
            self._journal("trial.started", {}, now_ns)
            return self._remember_result(event_id, kind, payload, {"receipt": receipt, "state": self.state(now_ns)})
        if kind == "trial.task_presented":
            if self.phase != "exploring":
                raise StudyError("invalid_phase")
            receipt = self.store.apply_event(self.attempt_id, event_id, kind, payload)
            return self._remember_result(event_id, kind, payload, {"receipt": receipt, "state": self.state(now_ns)})
        if kind == "control.stop":
            if self.phase != "exploring":
                raise StudyError("invalid_phase")
            self._journal("control.stop", {}, now_ns)
            receipt = {"attempt_id": self.attempt_id, "client_event_id": event_id,
                       "event_type": kind, "phase": self.phase, "status": "accepted"}
            return self._remember_result(event_id, kind, payload, {
                "receipt": receipt, "state": self.state(now_ns), "action": "stop"})
        if kind in {"answer.save", "answer.submit"}:
            if self.phase != "answering" or self.freeze_status != "ready":
                raise StudyError("answer_not_ready")
            if self.answer_deadline_ns is not None and now_ns >= self.answer_deadline_ns:
                self._timeout_answer(now_ns)
                raise StudyError("answer_deadline_elapsed")
            try:
                receipt = self.store.apply_event(self.attempt_id, event_id, kind, payload)
            except StudyStoreError:
                raise
            except Exception as error:
                state = self._abort("answer_persist_failed", now_ns)
                raise StudyError("answer_persist_failed", state=state) from error
            if kind == "answer.submit":
                self.phase = "completed"
                self.answer_status = receipt.get("answer_status", "submitted")
            return self._remember_result(event_id, kind, payload, {"receipt": receipt, "state": self.state(now_ns)})
        if kind == "questionnaire.submit":
            if self.phase != "completed":
                raise StudyError("invalid_phase")
            try:
                receipt = self.store.apply_event(self.attempt_id, event_id, kind, payload)
            except StudyStoreError:
                raise
            except Exception as error:
                # Questionnaire absence does not reverse a completed answer.
                state = dict(self.state(now_ns), error_code="questionnaire_persist_failed")
                raise StudyError("questionnaire_persist_failed", state=state) from error
            return self._remember_result(event_id, kind, payload, {"receipt": receipt, "state": self.state(now_ns)})
        raise StudyError("unsupported_event")

    def poll(self, now_ns: int) -> list[dict]:
        events = []
        if self.phase == "exploring":
            try:
                evidence = self.store.get_evidence_status(self.attempt_id)
                if (evidence.get("failed_jobs") or
                        self.store.get_attempt(self.attempt_id).get("evidence_failure")):
                    return [self._abort("evidence_persist_failed", now_ns)]
            except Exception:
                return [self._abort("evidence_persist_failed", now_ns)]
        if self.phase == "preparing" and self._startup_render is not None:
            try:
                status = self.render_tracker.status(self.attempt_id, self._startup_render["token"])
                evidence = self.store.get_evidence_status(self.attempt_id)
                if status.get("failed"):
                    return [self._abort("initial_render_failed", now_ns)]
                if evidence.get("failed_jobs") or self.store.get_attempt(self.attempt_id).get("evidence_failure"):
                    return [self._abort("evidence_persist_failed", now_ns)]
                revision = self._startup_render["dashboard_revision"]
                if now_ns >= self._startup_deadline_ns:
                    return [self._abort("initial_readiness_timeout", now_ns)]
                if status.get("complete") and self.store.evidence_ready(self.attempt_id, revision):
                    receipt = self._apply_internal("trial.ready", {})
                    self.phase = "ready"
                    self._journal("trial.ready", {"dashboard_revision": revision}, now_ns)
                    events.append(self.state(now_ns, receipt=receipt))
            except Exception:
                events.append(self._abort("evidence_persist_failed", now_ns))
        if self.phase == "answering" and self.freeze_status == "pending":
            try:
                status = self.render_tracker.status(self.attempt_id, self._frozen_render["token"])
                evidence = self.store.get_evidence_status(self.attempt_id)
                failed_jobs = evidence.get("failed_jobs") or []
                if status.get("failed"):
                    return [self._abort("frozen_render_failed", now_ns)]
                if failed_jobs or self.store.get_attempt(self.attempt_id).get("evidence_failure"):
                    return [self._abort("evidence_persist_failed", now_ns)]
                revision = self._frozen["frozen_committed_revision"]
                if now_ns >= self._readiness_deadline_ns:
                    events.append(self._abort("frozen_readiness_timeout", now_ns))
                elif status.get("complete") and self.store.evidence_ready(self.attempt_id, revision):
                    receipt = self._apply_internal("trial.answering", {})
                    self.freeze_status = "ready"
                    self.answer_deadline_ns = now_ns + self.answer_limit_ns
                    self._journal("trial.answering_ready", {"frozen_revision": revision}, now_ns)
                    events.append(self.state(now_ns, receipt=receipt))
            except Exception:
                events.append(self._abort("evidence_persist_failed", now_ns))
        if (self.phase == "answering" and self.freeze_status == "ready" and
                self.answer_deadline_ns is not None and now_ns >= self.answer_deadline_ns):
            try:
                events.append(self._timeout_answer(now_ns))
            except Exception:
                events.append(self._abort("answer_persist_failed", now_ns))
        return events

    def abort(self, reason: str, now_ns: int) -> dict:
        if self.phase in {"completed", "aborted"}:
            return self.state(now_ns)
        return self._abort(reason, now_ns)

    def state(self, now_ns: int, **extra) -> dict:
        remaining_ms = None
        if self.phase == "exploring" and self.exploration_deadline_ns is not None:
            remaining_ms = max(0, (self.exploration_deadline_ns - now_ns) // 1_000_000)
        elif self.phase == "answering" and self.freeze_status == "ready" and self.answer_deadline_ns is not None:
            remaining_ms = max(0, (self.answer_deadline_ns - now_ns) // 1_000_000)
        evidence_status = self.store.get_evidence_status(self.attempt_id)
        evidence_refs = (self.store.get_evidence_refs(self.attempt_id)
                         if hasattr(self.store, "get_evidence_refs")
                         else [{"revision": revision, "artifact_id": f"revision-{revision}"}
                               for revision in evidence_status.get("ready_revisions", [])])
        event = {
            "type": "trial.state", "phase": self.phase,
            "freeze_status": self.freeze_status, "remaining_ms": remaining_ms,
            "answer_status": self.answer_status,
            "evidence_refs_ready": deepcopy(evidence_refs),
            "allowed_actions": self._allowed_actions(),
        }
        if self.phase in {"exploring", "answering", "completed"}:
            event["task"] = deepcopy(self.assignment.get("task", {"task_id": self.assignment["task_id"]}))
        event.update(deepcopy(extra))
        return event

    def _allowed_actions(self):
        if self.phase == "ready":
            return ["trial.start"]
        if self.phase == "exploring":
            return ["trial.task_presented", "control.stop"]
        if self.phase == "answering" and self.freeze_status == "ready":
            return ["answer.save", "answer.submit"]
        if self.phase == "completed":
            return ["questionnaire.submit"]
        return []

    def _validate_control(self, event):
        if not isinstance(event, dict):
            raise StudyError("invalid_event")
        if _IDENTITY_FIELDS.intersection(event):
            raise StudyError("forged_identity", "client study events cannot contain identity fields")
        kind = event.get("type")
        event_id = event.get("client_event_id")
        if not isinstance(kind, str) or not isinstance(event_id, str) or not _SAFE_ID.fullmatch(event_id):
            raise StudyError("invalid_event")
        allowed = {
            "trial.start": set(), "trial.task_presented": set(), "control.stop": set(),
            "answer.save": {"draft_version", "conclusion", "evidence_refs", "limitations"},
            "answer.submit": {"submission_id", "conclusion", "evidence_refs", "limitations"},
            "questionnaire.submit": {"responses"},
        }
        if kind not in allowed:
            raise StudyError("unsupported_event")
        payload = {key: deepcopy(value) for key, value in event.items()
                   if key not in {"type", "client_event_id"}}
        if set(payload) != allowed[kind]:
            raise StudyError("invalid_payload")
        return kind, event_id, payload

    def _snapshot(self, snapshot):
        if not isinstance(snapshot, dict) or type(snapshot.get("dashboard_revision")) is not int:
            raise StudyError("invalid_snapshot")
        return deepcopy(snapshot)

    def _enqueue_evidence(self, snapshot, now_ns, reason):
        revision = snapshot["dashboard_revision"]
        if revision not in self._enqueued_revisions:
            provenance = {"reason": reason, "captured_ns": now_ns}
            if self.renderer_version:
                provenance["renderer_version"] = self.renderer_version
            self.store.enqueue_evidence(self.attempt_id, snapshot, provenance)
            self._enqueued_revisions.add(revision)

    def _apply_internal(self, event_type, payload):
        return self.store.apply_event(self.attempt_id, "server:" + uuid4().hex, event_type, payload)

    def _timeout_answer(self, now_ns):
        receipt = self._apply_internal("answer.timeout", {})
        self.phase = "completed"
        self.answer_status = receipt.get("answer_status", "empty")
        return self.state(now_ns, receipt=receipt)

    def _remember_result(self, event_id, kind, payload, result):
        saved = deepcopy(result)
        self._client_results[event_id] = (kind, deepcopy(payload), deepcopy(saved["receipt"]))
        return deepcopy(saved)

    def _abort(self, reason, now_ns):
        self._gate_open = False
        self.phase = "aborted"
        self.freeze_status = "failed" if self.freeze_status == "pending" else self.freeze_status
        try:
            self._apply_internal("trial.abort", {"reason_code": self._safe_reason(reason)})
        except Exception:
            pass
        self._journal("trial.aborted", {"reason_code": self._safe_reason(reason)}, now_ns)
        return dict(self.state(now_ns), error_code=self._safe_reason(reason))

    def _journal(self, event, metadata, now_ns):
        try:
            self.store.append_event(self.attempt_id, event, metadata, now_ns)
        except Exception:
            if event != "trial.aborted":
                raise

    @staticmethod
    def _safe_reason(reason):
        if isinstance(reason, str) and _SAFE_ID.fullmatch(reason):
            return reason
        return "study_error"
