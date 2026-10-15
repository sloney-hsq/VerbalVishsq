#!/usr/bin/env python3
"""Deterministic, privacy-minimizing summaries for Trace v2 JSONL files."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ANALYZER_VERSION = "1.0.0"
CANONICAL_CONDITIONS = {"turn_taking", "revision_enabled"}
CONTEXT_FIELDS = ("participant_id", "trial_id", "task_id", "dataset_id", "condition")
CORRELATION_FIELDS = ("request_id", "previous_request_id", "batch_id", "call_id")
SAFE_DATA_FIELDS = (
    "received_at_monotonic_ns", "in_flight", "to_phase", "execution_status",
    "commit_status", "state_changed", "call_ids",
)
TERMINAL_PHASES = {"settled", "failed", "superseded"}
EXECUTION_STATUSES = {"succeeded", "failed"}
COMMIT_STATUSES = {"committed", "read_only", "no_change", "superseded", "conflicted", "failed"}
KNOWN_EVENTS = {
    "session.started", "session.closed", "session.background_error",
    "user.request_received", "request.received", "revision.received",
    "response.superseded", "request.phase_changed", "request.settled", "request.failed",
    "response.started", "response.created", "response.done", "response.finished",
    "assistant.playback_started", "assistant.playback_finished", "speech.started",
    "intent.decision", "intent.revoked", "input.rejected", "asr.stale_discard",
    "browser.sent", "stale.discard", "provider.cancel_race", "batch.rejected",
    "batch.outcome", "call.started", "call.finished", "tool.execution_started",
    "tool.execution_finished", "dashboard.commit_started", "dashboard.committed",
    "dashboard.commit_rejected", "commit.rejected",
}


def _is_nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


class _Diagnostics:
    def __init__(self):
        self._items: dict[tuple[str, str | None], set[int]] = defaultdict(set)
        self._counts: dict[tuple[str, str | None], int] = defaultdict(int)

    def add(self, code: str, line: int | None = None, session_id: str | None = None):
        key = (code, session_id)
        self._counts[key] += 1
        if line is not None:
            self._items[key].add(line)

    def render(self, *, session_id: str | None = None) -> list[dict[str, Any]]:
        rows = []
        for (code, owner), count in sorted(self._counts.items(), key=lambda item: (item[0][1] or "", item[0][0])):
            if session_id is not None and owner != session_id:
                continue
            if session_id is None and owner is not None:
                continue
            row: dict[str, Any] = {"code": code, "count": count}
            lines = sorted(self._items.get((code, owner), ()))
            if lines:
                row["lines"] = lines
            if owner is not None:
                row["session_id"] = owner
            rows.append(row)
        return rows

    def count(self, *, session_id: str | None = None) -> int:
        return sum(count for (code, owner), count in self._counts.items()
                   if session_id is None or owner == session_id)


def _safe_projection(row: dict[str, Any]) -> dict[str, Any]:
    """Read only fields needed for validation, correlation, and metric derivation."""
    correlation = row.get("correlation")
    if not isinstance(correlation, dict):
        correlation = {}
    data = row.get("data")
    if not isinstance(data, dict):
        data = {}
    return {
        "schema_version": row.get("schema_version"),
        "seq": row.get("seq"),
        "session_id": row.get("session_id"),
        **{name: row.get(name) for name in CONTEXT_FIELDS},
        "observed_at": row.get("observed_at"),
        "monotonic_ns": row.get("monotonic_ns"),
        "event": row.get("event"),
        "correlation": {name: correlation.get(name) for name in CORRELATION_FIELDS},
        "data": {name: data.get(name) for name in SAFE_DATA_FIELDS if name in data},
    }


def _valid_record(row: Any, line_no: int, diagnostics: _Diagnostics) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        diagnostics.add("record_not_object", line_no)
        return None
    if row.get("schema_version") != 2 or type(row.get("schema_version")) is not int:
        diagnostics.add("unsupported_schema", line_no)
        return None
    missing = [name for name in ("session_id", *CONTEXT_FIELDS, "seq", "event", "observed_at", "monotonic_ns", "correlation", "data")
               if name not in row]
    if missing:
        diagnostics.add("missing_required_field", line_no)
        return None
    if not _is_nonempty_string(row.get("session_id")):
        diagnostics.add("invalid_session_id", line_no)
        return None
    if not _is_nonnegative_int(row.get("seq")) or row["seq"] == 0:
        diagnostics.add("invalid_seq", line_no)
        return None
    if not _is_nonempty_string(row.get("event")):
        diagnostics.add("invalid_event", line_no)
        return None
    if not _is_nonnegative_int(row.get("monotonic_ns")):
        diagnostics.add("invalid_monotonic_ns", line_no)
        return None
    if not isinstance(row.get("observed_at"), str):
        diagnostics.add("invalid_observed_at", line_no)
        return None
    try:
        datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
    except (TypeError, ValueError):
        diagnostics.add("invalid_observed_at", line_no)
        return None
    for name in CONTEXT_FIELDS[:-2]:
        value = row.get(name)
        if value is not None and not isinstance(value, str):
            diagnostics.add("invalid_context", line_no)
            return None
    if not _is_nonempty_string(row.get("dataset_id")):
        diagnostics.add("invalid_context", line_no)
        return None
    if not isinstance(row.get("condition"), str) or row["condition"] not in CANONICAL_CONDITIONS:
        diagnostics.add("invalid_context", line_no)
        return None
    if not isinstance(row.get("correlation"), dict) or not isinstance(row.get("data"), dict):
        diagnostics.add("invalid_record_shape", line_no)
        return None
    # Correlation IDs used by this analyzer must be strings when present.
    for name in CORRELATION_FIELDS:
        value = row["correlation"].get(name)
        if value is not None and not isinstance(value, str):
            diagnostics.add("invalid_correlation", line_no)
            return None
    # Copy only the safe projection. Consent-controlled values are never read by metric code.
    return {"line": line_no, **_safe_projection(row)}


def _ms(delta_ns: int) -> float | None:
    if type(delta_ns) is not int or delta_ns < 0:
        return None
    try:
        value = round(delta_ns / 1_000_000, 6)
    except (OverflowError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _identity(record: dict[str, Any], field: str) -> str | None:
    value = record["correlation"].get(field)
    return value if _is_nonempty_string(value) else None


def _safe_event_data(record: dict[str, Any]) -> dict[str, Any]:
    return record["data"]


def _summarize_session(session_id: str, records: list[dict[str, Any]],
                       diagnostics: _Diagnostics) -> dict[str, Any]:
    context = {name: records[0][name] for name in CONTEXT_FIELDS}
    ordered = sorted(records, key=lambda row: (row["seq"], row["line"]))
    # Duplicate semantic records are diagnosed and only the first sequence occurrence is used.
    semantic_seen: set[tuple[str, str]] = set()
    semantic_records: list[dict[str, Any]] = []
    for row in ordered:
        event = row["event"]
        identity_field = None
        if event in {"user.request_received", "request.received", "revision.received",
                     "request.settled", "request.failed", "request.phase_changed"}:
            identity_field = "request_id"
        elif event in {"batch.outcome", "dashboard.committed"}:
            identity_field = "batch_id"
        identity = _identity(row, identity_field) if identity_field else None
        if identity is not None:
            extra = ""
            if event == "request.phase_changed":
                phase = _safe_event_data(row).get("to_phase")
                extra = f":{phase}" if isinstance(phase, str) else ":invalid"
            key = (event, identity + extra)
            if key in semantic_seen:
                diagnostics.add("duplicate_semantic_event", row["line"], session_id)
                continue
            semantic_seen.add(key)
        semantic_records.append(row)

    known = [row for row in semantic_records if row["event"] in KNOWN_EVENTS]
    for row in semantic_records:
        if row["event"] not in KNOWN_EVENTS:
            diagnostics.add("unknown_event", row["line"], session_id)

    starts = [row for row in known if row["event"] == "session.started"]
    closes = [row for row in known if row["event"] == "session.closed"]
    if not starts:
        diagnostics.add("missing_session_start", session_id=session_id)
    if not closes:
        diagnostics.add("missing_session_close", session_id=session_id)
    if len(starts) > 1:
        diagnostics.add("duplicate_session_start", starts[1]["line"], session_id)
    if len(closes) > 1:
        diagnostics.add("duplicate_session_close", closes[1]["line"], session_id)
    start_ns = starts[0]["monotonic_ns"] if starts else None
    if starts and closes:
        duration_end = closes[0]["monotonic_ns"]
        duration_complete = True
    elif starts and records:
        duration_end = max(records, key=lambda row: (row["seq"], row["line"]))["monotonic_ns"]
        duration_complete = False
    else:
        duration_end = None
        duration_complete = False
    duration_ms = None
    if start_ns is not None and duration_end is not None:
        duration_delta = duration_end - start_ns
        duration_ms = _ms(duration_delta)
        if duration_ms is None:
            diagnostics.add("negative_duration" if duration_delta < 0 else "timing_overflow", session_id=session_id)

    canonical_receives = [row for row in known if row["event"] == "user.request_received"]
    canonical_ids = {_identity(row, "request_id") for row in canonical_receives}
    canonical_ids.discard(None)
    fallback = []
    for row in known:
        if row["event"] not in {"request.received", "revision.received"}:
            continue
        if row["event"] == "revision.received" and _safe_event_data(row).get("in_flight") is not True:
            continue
        request_id = _identity(row, "request_id")
        if request_id is not None and request_id not in canonical_ids:
            fallback.append(row)
    if fallback:
        diagnostics.add("request_count_fallback", session_id=session_id)
    receive_rows = [*canonical_receives, *fallback]
    requests: dict[str, dict[str, Any]] = {}
    receive_order: list[str] = []
    for row in receive_rows:
        request_id = _identity(row, "request_id")
        if request_id is None:
            diagnostics.add("missing_request_id", row["line"], session_id)
            continue
        if request_id in requests:
            continue
        received_ns = _safe_event_data(row).get("received_at_monotonic_ns")
        if not _is_nonnegative_int(received_ns):
            received_ns = None
            diagnostics.add("missing_request_timestamp", row["line"], session_id)
        requests[request_id] = {"received_ns": received_ns, "seq": row["seq"], "terminal": []}
        receive_order.append(request_id)

    revisions: dict[str, dict[str, Any]] = {}
    for row in known:
        if row["event"] != "revision.received":
            continue
        data = _safe_event_data(row)
        request_id = _identity(row, "request_id")
        if request_id is None:
            diagnostics.add("missing_request_id", row["line"], session_id)
            continue
        if data.get("in_flight") is not True:
            diagnostics.add("invalid_revision_flag", row["line"], session_id)
            continue
        previous_request_id = _identity(row, "previous_request_id")
        if previous_request_id is None:
            diagnostics.add("missing_previous_request_id", row["line"], session_id)
        received_ns = data.get("received_at_monotonic_ns")
        if not _is_nonnegative_int(received_ns):
            diagnostics.add("missing_revision_timestamp", row["line"], session_id)
            received_ns = None
        revisions[request_id] = {
            "previous_request_id": previous_request_id,
            "received_ns": received_ns,
            "seq": row["seq"],
        }
        if request_id not in requests:
            # A revision event is also a valid fallback request record if canonical receive is absent.
            if not canonical_receives:
                requests[request_id] = {"received_ns": received_ns if _is_nonnegative_int(received_ns) else None,
                                        "seq": row["seq"], "terminal": []}
                receive_order.append(request_id)

    settled_ns: dict[str, int] = {}
    terminal_by_request: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in known:
        event = row["event"]
        phase = _safe_event_data(row).get("to_phase")
        if event not in {"request.settled", "request.failed", "request.phase_changed"}:
            continue
        if event == "request.phase_changed" and (not isinstance(phase, str) or phase not in TERMINAL_PHASES):
            continue
        request_id = _identity(row, "request_id")
        if request_id is None:
            diagnostics.add("missing_request_id", row["line"], session_id)
            continue
        terminal_by_request[request_id].append(row)
        if event == "request.settled":
            settled_ns.setdefault(request_id, row["monotonic_ns"])

    for request_id, info in requests.items():
        terminals = terminal_by_request.get(request_id, [])
        if not terminals:
            diagnostics.add("missing_request_terminal", session_id=session_id)
        else:
            info["terminal"] = sorted(terminals, key=lambda row: (row["seq"], row["line"]))

    time_to_final_state_ms = None
    if receive_order:
        final_id = max(receive_order, key=lambda request_id: (requests[request_id]["seq"], request_id))
        info = requests[final_id]
        if info["received_ns"] is not None and info["terminal"]:
            first_terminal = info["terminal"][0]
            final_delta = first_terminal["monotonic_ns"] - info["received_ns"]
            time_to_final_state_ms = _ms(final_delta)
            if time_to_final_state_ms is None:
                diagnostics.add("negative_request_duration" if final_delta < 0 else "timing_overflow",
                                first_terminal["line"], session_id)

    revision_windows: list[float | None] = []
    revision_rows = sorted(revisions.values(), key=lambda revision: revision["seq"])
    for revision in revision_rows:
        previous_id = revision["previous_request_id"]
        received_ns = revision["received_ns"]
        settled = settled_ns.get(previous_id) if previous_id else None
        window = None
        if _is_nonnegative_int(received_ns) and settled is not None:
            window_delta = settled - received_ns
            window = _ms(window_delta)
            if window is None:
                diagnostics.add("negative_saving_window" if window_delta < 0 else "timing_overflow",
                                session_id=session_id)
        revision_windows.append(window)
    revision_saving_window_ms = revision_windows[-1] if len(revision_windows) == 1 else None

    superseded_batches: set[str] = set()
    superseded_calls: set[tuple[str, str]] = set()
    for row in known:
        if row["event"] != "batch.outcome":
            continue
        batch_id = _identity(row, "batch_id")
        data = _safe_event_data(row)
        if batch_id is None:
            diagnostics.add("missing_batch_id", row["line"], session_id)
            continue
        execution_status = data.get("execution_status")
        commit_status = data.get("commit_status")
        state_changed = data.get("state_changed")
        call_ids = data.get("call_ids")
        valid_outcome = (
            isinstance(execution_status, str) and execution_status in EXECUTION_STATUSES and
            isinstance(commit_status, str) and commit_status in COMMIT_STATUSES and
            type(state_changed) is bool and isinstance(call_ids, list) and
            state_changed == (commit_status == "committed")
        )
        if valid_outcome:
            valid_outcome = (
                (commit_status == "committed" and execution_status == "succeeded") or
                (commit_status in {"read_only", "no_change"} and execution_status == "succeeded") or
                (commit_status == "failed" and execution_status == "failed") or
                (commit_status == "superseded" and execution_status in EXECUTION_STATUSES) or
                (commit_status == "conflicted" and execution_status == "succeeded")
            )
        if not valid_outcome:
            diagnostics.add("invalid_batch_outcome", row["line"], session_id)
            continue
        if commit_status != "superseded":
            continue
        superseded_batches.add(batch_id)
        for call_id in call_ids:
            if _is_nonempty_string(call_id):
                # Providers may reuse call IDs in separate batches; count the scoped identity.
                superseded_calls.add((batch_id, call_id))
            else:
                diagnostics.add("invalid_call_id", row["line"], session_id)

    dashboard_batches: set[str] = set()
    for row in known:
        if row["event"] != "dashboard.committed":
            continue
        batch_id = _identity(row, "batch_id")
        if batch_id is None:
            diagnostics.add("missing_batch_id", row["line"], session_id)
        else:
            dashboard_batches.add(batch_id)

    return {
        "session_id": session_id,
        **context,
        "duration_ms": duration_ms,
        "duration_complete": duration_complete,
        "request_count": len(requests),
        "in_flight_revision_count": len(revisions),
        "superseded_batch_count": len(superseded_batches),
        "superseded_call_count": len(superseded_calls),
        "dashboard_commit_count": len(dashboard_batches),
        "time_to_final_state_ms": time_to_final_state_ms,
        "revision_saving_window_ms": revision_saving_window_ms,
        "revision_saving_windows_ms": revision_windows,
        "diagnostics": diagnostics.render(session_id=session_id),
    }


def analyze_lines(lines: Iterable[str], *, source_name: str = "trace.jsonl") -> dict[str, Any]:
    """Analyze physical JSONL lines while retaining only a metric-safe projection."""
    diagnostics = _Diagnostics()
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    contexts: dict[str, tuple[Any, ...]] = {}
    seq_rows: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    last_physical_seq: dict[str, int] = {}
    for line_no, physical_line in enumerate(lines, start=1):
        if not physical_line.strip():
            continue
        try:
            parsed = json.loads(physical_line)
        except (json.JSONDecodeError, UnicodeError, ValueError, RecursionError):
            diagnostics.add("malformed_json", line_no)
            continue
        row = _valid_record(parsed, line_no, diagnostics)
        if row is None:
            continue
        session_id = row["session_id"]
        context = tuple(row[name] for name in CONTEXT_FIELDS)
        if session_id in contexts and context != contexts[session_id]:
            diagnostics.add("context_conflict", line_no, session_id)
            continue
        contexts.setdefault(session_id, context)
        previous_seq = last_physical_seq.get(session_id)
        if previous_seq is not None and row["seq"] < previous_seq:
            diagnostics.add("physical_reordering", line_no, session_id)
        last_physical_seq[session_id] = row["seq"]
        existing = seq_rows[session_id].get(row["seq"])
        if existing is not None:
            if {key: value for key, value in existing.items() if key != "line"} == {key: value for key, value in row.items() if key != "line"}:
                diagnostics.add("duplicate_record", line_no, session_id)
            else:
                diagnostics.add("sequence_conflict", line_no, session_id)
            continue  # deterministic first-physical-line wins for a conflicting sequence
        seq_rows[session_id][row["seq"]] = row
        sessions[session_id].append(row)

    trials: list[dict[str, Any]] = []
    for session_id in sorted(sessions):
        records = sorted(sessions[session_id], key=lambda row: (row["seq"], row["line"]))
        if records:
            seqs = [row["seq"] for row in records]
            unique_seq_count = len({row["seq"] for row in records})
            if seqs[0] != 1 or seqs[-1] - seqs[0] + 1 > unique_seq_count:
                diagnostics.add("sequence_gap", session_id=session_id)
        trials.append(_summarize_session(session_id, records, diagnostics))

    top_diagnostics = diagnostics.render()
    return {
        "schema_version": 1,
        "analyzer_version": ANALYZER_VERSION,
        "source": Path(source_name).name,
        "summary": {
            "trial_count": len(trials),
            "diagnostic_count": diagnostics.count(),
        },
        "trials": trials,
        "diagnostics": top_diagnostics,
    }


def analyze_jsonl(text: str, *, source_name: str = "trace.jsonl") -> dict[str, Any]:
    """Analyze JSONL text. A valid final record needs no trailing newline."""
    return analyze_lines(text.splitlines(), source_name=source_name)


def analyze_path(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        return analyze_lines(handle, source_name=source.name)


def _render(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize Trace v2 JSONL files without exposing consent-controlled content.")
    parser.add_argument("input", help="input Trace v2 JSONL path")
    parser.add_argument("--output", help="write report to this path instead of stdout")
    parser.add_argument("--strict", action="store_true", help="return exit code 1 when data-quality diagnostics exist")
    args = parser.parse_args(argv)
    if args.output and Path(args.input).resolve() == Path(args.output).resolve():
        parser.error("output path must not overwrite input trace")
    try:
        result = analyze_path(args.input)
    except (OSError, UnicodeError) as error:
        parser.error(f"cannot read input: {error.__class__.__name__}")
    output = _render(result)
    if args.output:
        try:
            Path(args.output).write_text(output, encoding="utf-8", newline="\n")
        except OSError as error:
            parser.error(f"cannot write output: {error.__class__.__name__}")
    else:
        print(output, end="")
    if args.strict and result["summary"]["diagnostic_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
