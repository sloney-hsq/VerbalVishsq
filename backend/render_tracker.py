"""Server-authoritative registration and acknowledgement of browser renders."""

from __future__ import annotations

from copy import deepcopy
import json
from math import isfinite
import re
from secrets import token_urlsafe
from threading import RLock


_EVENT_TYPES = {"view.rendered", "view.render_failed"}
_ERROR_CODES = {"embed_failed", "run_async_failed", "render_failed"}
_PRESENTATION_MODES = {"paged", "all", "empty"}
_EVENT_FIELDS = {
    "type", "client_event_id", "render_token", "dashboard_revision", "view_id",
    "view_revision", "render_generation", "browser_duration_ms", "presentation",
    "error_code",
}


class RenderTracker:
    """Track only the newest render envelope for each study attempt."""

    def __init__(self):
        self._lock = RLock()
        self._current: dict[str, str] = {}
        self._records: dict[str, dict] = {}

    def register(self, attempt_id: str, snapshot: dict, reason: str) -> dict:
        attempt_id = _required_token(attempt_id, "attempt_id")
        if not isinstance(snapshot, dict):
            raise ValueError("snapshot must be an object")
        revision = snapshot.get("dashboard_revision")
        if not _integer(revision, minimum=0):
            raise ValueError("snapshot dashboard_revision must be a non-negative integer")
        views = snapshot.get("views")
        if not isinstance(views, list):
            raise ValueError("snapshot views must be a list")
        expected = []
        seen = set()
        for view in views:
            if not isinstance(view, dict):
                raise ValueError("snapshot views must be objects")
            view_id = _required_token(view.get("id"), "view id")
            view_revision = view.get("view_revision")
            if not _integer(view_revision, minimum=0):
                raise ValueError("view_revision must be a non-negative integer")
            if view_id in seen:
                raise ValueError("snapshot view ids must be unique")
            seen.add(view_id)
            expected.append({"view_id": view_id, "view_revision": view_revision})
        reason = _required_token(reason, "reason")
        token = token_urlsafe(24)
        envelope = {
            "token": token,
            "dashboard_revision": revision,
            "expected_views": expected,
            "reason": reason,
        }
        with self._lock:
            previous = self._current.get(attempt_id)
            if previous in self._records:
                self._records[previous]["current"] = False
            self._current[attempt_id] = token
            self._records[token] = {
                "attempt_id": attempt_id,
                "current": True,
                "envelope": deepcopy(envelope),
                "expected": {(item["view_id"], item["view_revision"]) for item in expected},
                "acknowledged": set(),
                "events": {},
                "client_events": {},
                "latest_generation": {},
                "empty_acknowledged": False,
                "failed": False,
                "error_code": None,
            }
        return deepcopy(envelope)

    def ack(self, attempt_id: str, event: dict) -> dict:
        with self._lock:
            record = self._record(attempt_id, event.get("render_token") if isinstance(event, dict) else None)
            if record is None or not _valid_event(event, record):
                return self._result(record, accepted=False)
            event_id = event["client_event_id"]
            canonical = json.dumps(event, sort_keys=True, separators=(",", ":"))
            previous = record["client_events"].get(event_id)
            if previous is not None:
                if previous["canonical"] == canonical:
                    return deepcopy(previous["result"])
                return self._result(record, accepted=False, error_code="client_event_conflict")
            signature = _event_signature(event)
            if signature in record["events"]:
                result = deepcopy(record["events"][signature])
                record["client_events"][event_id] = {"canonical": canonical, "result": deepcopy(result)}
                return result
            if record["failed"]:
                return self._result(record, accepted=False)

            pair = (event.get("view_id"), event.get("view_revision"))
            latest = record["latest_generation"].get(pair)
            if latest and (
                event["render_generation"] < latest[0]
                or (event["render_generation"] == latest[0] and event["type"] != latest[1])
            ):
                return self._result(record, accepted=False, error_code="stale_render_generation")
            record["latest_generation"][pair] = (event["render_generation"], event["type"])
            if record["expected"]:
                record["acknowledged"].add(pair)
            else:
                record["empty_acknowledged"] = True
            if event["type"] == "view.render_failed":
                record["failed"] = True
                record["error_code"] = event["error_code"]
            result = self._result(record, accepted=True)
            record["events"][signature] = deepcopy(result)
            record["client_events"][event_id] = {"canonical": canonical, "result": deepcopy(result)}
            return result

    def status(self, attempt_id: str, token: str) -> dict:
        """Return readiness without changing tracker state."""
        with self._lock:
            return self._result(self._record(attempt_id, token), accepted=None)

    def _record(self, attempt_id, token):
        if not isinstance(attempt_id, str) or not isinstance(token, str):
            return None
        record = self._records.get(token)
        if (
            record is None
            or record["attempt_id"] != attempt_id
            or not record["current"]
            or self._current.get(attempt_id) != token
        ):
            return None
        return record

    @staticmethod
    def _result(record, *, accepted, error_code=None):
        if record is None:
            return {
                "accepted": False, "complete": False, "failed": False,
                "dashboard_revision": None, "error_code": "invalid_render_ack",
            }
        complete = (
            not record["failed"]
            and (record["acknowledged"] == record["expected"] if record["expected"]
                 else record["empty_acknowledged"])
        )
        return {
            "accepted": record["current"] if accepted is None else accepted,
            "complete": complete,
            "failed": record["failed"],
            "dashboard_revision": record["envelope"]["dashboard_revision"],
            "error_code": error_code or record["error_code"],
        }


def _valid_event(event, record):
    if not isinstance(event, dict) or not set(event).issubset(_EVENT_FIELDS):
        return False
    if not isinstance(event.get("type"), str) or event["type"] not in _EVENT_TYPES:
        return False
    if not isinstance(event.get("client_event_id"), str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", event["client_event_id"]):
        return False
    envelope = record["envelope"]
    if not isinstance(event.get("render_token"), str) or event["render_token"] != envelope["token"]:
        return False
    if not _integer(event.get("dashboard_revision"), minimum=0) or event["dashboard_revision"] != envelope["dashboard_revision"]:
        return False
    if not _integer(event.get("render_generation"), minimum=0):
        return False
    duration = event.get("browser_duration_ms")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not isfinite(duration) or duration < 0:
        return False
    presentation = event.get("presentation")
    if not isinstance(presentation, dict) or set(presentation) != {"mode", "page_index"}:
        return False
    if not isinstance(presentation["mode"], str) or presentation["mode"] not in _PRESENTATION_MODES:
        return False
    page_index = presentation["page_index"]
    if page_index is not None and not _integer(page_index, minimum=0):
        return False
    pair = (event.get("view_id"), event.get("view_revision"))
    if record["expected"]:
        if not isinstance(pair[0], str) or not _integer(pair[1], minimum=0):
            return False
        if pair not in record["expected"] or presentation["mode"] == "empty":
            return False
    elif pair != (None, None) or presentation != {"mode": "empty", "page_index": None}:
        return False
    if event["type"] == "view.render_failed":
        return isinstance(event.get("error_code"), str) and event["error_code"] in _ERROR_CODES
    return event.get("error_code") in (None, "")


def _event_signature(event):
    presentation = event["presentation"]
    return (
        event["type"], event.get("view_id"), event.get("view_revision"),
        event["render_generation"], presentation["mode"], presentation["page_index"],
        event.get("error_code"),
    )


def _required_token(value, label):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{label} must be a 1-128 character string")
    return value


def _integer(value, *, minimum):
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum
