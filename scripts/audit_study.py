#!/usr/bin/env python3
"""Reconcile planned assignments with durable study attempts and Trace v2 summaries."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.study_store import StudyStore
from scripts.analyze_traces import analyze_path


AUDITOR_VERSION = "1.0.0"


def _diagnostic(code, **fields):
    return {"code": code, **{key: value for key, value in fields.items() if value is not None}}


def audit_assignments(schedule: dict, attempts: list[dict],
                      trace_summaries: list[dict]) -> dict:
    """Audit assignment-level outcomes; attempts never inflate the denominator."""
    if not isinstance(schedule, dict) or not isinstance(schedule.get("assignments"), list):
        raise ValueError("invalid schedule")
    if not isinstance(attempts, list) or not isinstance(trace_summaries, list):
        raise ValueError("attempts and trace_summaries must be lists")
    diagnostics = []
    plans = schedule["assignments"]
    planned = {}
    participants = defaultdict(list)
    for row in plans:
        if not isinstance(row, dict) or not isinstance(row.get("assignment_id"), str):
            raise ValueError("invalid schedule assignment")
        assignment_id = row["assignment_id"]
        if assignment_id in planned:
            diagnostics.append(_diagnostic("duplicate_planned_assignment", assignment_id=assignment_id))
            continue
        planned[assignment_id] = row
        participants[row.get("participant_id")].append(row)
    if len(planned) != 12:
        diagnostics.append(_diagnostic("planned_count", expected=12, actual=len(planned)))
    condition_counts = Counter(row.get("condition") for row in planned.values())
    if condition_counts != Counter({"revision_enabled": 6, "turn_taking": 6}):
        diagnostics.append(_diagnostic("condition_balance", expected=6,
                                       actual=dict(sorted(condition_counts.items()))))
    cell_counts = Counter((row.get("task_id"), row.get("condition")) for row in planned.values())
    if set(cell_counts.values()) != {3} or len(cell_counts) != 4:
        diagnostics.append(_diagnostic("task_condition_balance", expected=3,
                                       actual={"|".join(map(str, key)): value
                                               for key, value in sorted(cell_counts.items())}))
    for participant_id, rows in participants.items():
        if len(rows) != 1:
            diagnostics.append(_diagnostic("second_formal_task", participant_id=participant_id,
                                           planned_count=len(rows)))

    practice = [row for row in attempts if row.get("is_practice") is True]
    formal = [row for row in attempts if row.get("is_practice") is not True]
    by_assignment = defaultdict(list)
    seen_attempts = set()
    seen_sessions = set()
    formal_by_participant = defaultdict(set)
    for row in formal:
        attempt_id = row.get("attempt_id")
        session_id = row.get("session_id")
        if attempt_id in seen_attempts:
            diagnostics.append(_diagnostic("duplicate_attempt_id", attempt_id=attempt_id))
        seen_attempts.add(attempt_id)
        if session_id in seen_sessions:
            diagnostics.append(_diagnostic("duplicate_session_id", session_id=session_id))
        seen_sessions.add(session_id)
        assignment_id = row.get("assignment_id")
        participant_id = row.get("participant_id")
        formal_by_participant[participant_id].add((assignment_id, row.get("task_id")))
        if assignment_id not in planned:
            diagnostics.append(_diagnostic("unplanned_attempt", assignment_id=assignment_id,
                                           participant_id=participant_id, attempt_id=attempt_id))
            continue
        by_assignment[assignment_id].append(row)
    for participant_id, identities in formal_by_participant.items():
        planned_identity = {(row["assignment_id"], row["task_id"])
                            for row in participants.get(participant_id, [])}
        if len(identities | planned_identity) > 1:
            diagnostics.append(_diagnostic("second_formal_task", participant_id=participant_id,
                                           observed_count=len(identities)))

    trace_by_session = defaultdict(list)
    for trace in trace_summaries:
        if isinstance(trace, dict) and "_trace_diagnostics" in trace:
            diagnostics.append(_diagnostic("trace_diagnostics", source=trace.get("source"),
                                           count=trace["_trace_diagnostics"]))
            continue
        if isinstance(trace, dict) and isinstance(trace.get("session_id"), str):
            trace_by_session[trace["session_id"]].append(trace)

    rows = []
    completed = aborted = started = 0
    for assignment_id, plan in sorted(planned.items()):
        input_order = {id(row): index for index, row in enumerate(attempts)}
        observed = sorted(by_assignment.get(assignment_id, []), key=lambda row: (
            row.get("created_ns") if type(row.get("created_ns")) is int else input_order[id(row)],
            input_order[id(row)], str(row.get("attempt_id", "")),
        ))
        base = {key: plan.get(key) for key in
                ("assignment_id", "participant_id", "trial_id", "task_id", "condition")}
        if not observed:
            diagnostics.append(_diagnostic("missing_assignment", assignment_id=assignment_id,
                                           participant_id=plan.get("participant_id")))
            rows.append({**base, "status": "missing", "attempt_count": 0})
            continue
        started += 1
        invalid = False
        if len(observed) > 1:
            diagnostics.append(_diagnostic("multiple_attempts", assignment_id=assignment_id,
                                           count=len(observed)))
            if any(row.get("task_exposed") is True for row in observed[:-1]):
                diagnostics.append(_diagnostic("retry_after_exposure", assignment_id=assignment_id))
                invalid = True
        for item in observed:
            for field in ("participant_id", "trial_id", "task_id", "condition", "dataset_id",
                          "study_id", "study_version", "manifest_sha256"):
                if item.get(field) != plan.get(field):
                    diagnostics.append(_diagnostic(f"{field}_mismatch", assignment_id=assignment_id,
                                                   attempt_id=item.get("attempt_id")))
                    invalid = True
            traces = trace_by_session.get(item.get("session_id"), [])
            if not traces:
                diagnostics.append(_diagnostic("missing_trace", assignment_id=assignment_id,
                                               session_id=item.get("session_id")))
            if len(traces) > 1:
                diagnostics.append(_diagnostic("duplicate_trace_session", assignment_id=assignment_id,
                                               session_id=item.get("session_id")))
            for trace in traces:
                for field in ("participant_id", "trial_id", "task_id", "condition"):
                    if trace.get(field) != plan.get(field):
                        diagnostics.append(_diagnostic("trace_context_mismatch",
                                                       assignment_id=assignment_id, field=field))
        latest = observed[-1]
        if invalid:
            status = "invalid"
        elif latest.get("phase") == "completed":
            status = "completed"
            completed += 1
        elif latest.get("phase") == "aborted":
            status = "aborted"
            aborted += 1
        else:
            status = "started"
        rows.append({**base, "status": status, "attempt_count": len(observed),
                     "answer_status": latest.get("answer_status")})

    diagnostics.sort(key=lambda row: (row["code"], str(row.get("assignment_id", "")),
                                      str(row.get("participant_id", ""))))
    return {
        "schema_version": 1, "auditor_version": AUDITOR_VERSION,
        "planned": len(planned), "started": started, "completed": completed,
        "aborted": aborted, "missing": len(planned) - started,
        "practice_attempts": len(practice), "formal_attempts": len(formal),
        "assignments": rows, "diagnostics": diagnostics,
    }


def _atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                    sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit the fixed VerbalVis between-subject study.")
    parser.add_argument("--schedule", required=True, type=Path)
    parser.add_argument("--study-data", required=True, type=Path)
    parser.add_argument("--traces", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        schedule = json.loads(args.schedule.read_text(encoding="utf-8"))
        if not args.study_data.is_dir() or not (args.study_data / "study.sqlite3").is_file():
            raise ValueError(f"study database does not exist: {args.study_data}")
        attempts = StudyStore(args.study_data).list_attempts()
        traces = []
        if args.traces:
            paths = [args.traces] if args.traces.is_file() else sorted(args.traces.glob("*.jsonl"))
            for path in paths:
                analysis = analyze_path(path)
                traces.extend(analysis.get("trials", []))
                if analysis.get("diagnostics"):
                    traces.append({"_trace_diagnostics": len(analysis["diagnostics"]),
                                   "source": path.name})
        result = audit_assignments(schedule, attempts, traces)
        if args.output:
            if args.output.exists():
                raise ValueError(f"output already exists: {args.output}")
            _atomic_json(args.output, result)
        else:
            sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return 1 if args.strict and result["diagnostics"] else 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"audit_study: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

