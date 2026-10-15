#!/usr/bin/env python3
"""Reconcile planned VerbalVis trials with privacy-safe Trace v2 summaries."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from refactor_next.backend.conditions import CANONICAL_CONDITIONS
from scripts.analyze_traces import analyze_path


AUDITOR_VERSION = "1.0.0"


def _text(value):
    return value if isinstance(value, str) and value.strip() else None


def _diagnostic(code, **context):
    return {"code": code, **{key: value for key, value in context.items() if value is not None}}


def _load_schedule(path):
    try:
        row = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid schedule {Path(path).name}: {exc}") from exc
    required = ("study_id", "dataset_id", "manifest_version", "manifest_sha256",
                "participant_id", "sequence_id")
    if not isinstance(row, dict) or row.get("schema_version") != 1:
        raise ValueError(f"invalid schedule schema: {Path(path).name}")
    if any(_text(row.get(field)) is None for field in required):
        raise ValueError(f"schedule context is incomplete: {Path(path).name}")
    trials = row.get("trials")
    if not isinstance(trials, list) or not trials:
        raise ValueError(f"schedule has no trials: {Path(path).name}")
    normalized = []
    for trial in trials:
        if not isinstance(trial, dict):
            raise ValueError(f"schedule trial is not an object: {Path(path).name}")
        trial_id, task_id, condition = (
            _text(trial.get("trial_id")), _text(trial.get("task_id")), trial.get("condition")
        )
        if trial_id is None or task_id is None or condition not in CANONICAL_CONDITIONS:
            raise ValueError(f"schedule trial context is invalid: {Path(path).name}")
        normalized.append({
            "participant_id": row["participant_id"],
            "trial_id": trial_id,
            "task_id": task_id,
            "dataset_id": row["dataset_id"],
            "condition": condition,
            "trial_index": trial.get("trial_index"),
        })
    return {
        "study_id": row["study_id"],
        "dataset_id": row["dataset_id"],
        "manifest_version": row["manifest_version"],
        "manifest_sha256": row["manifest_sha256"],
        "participant_id": row["participant_id"],
        "sequence_id": row["sequence_id"],
        "trials": normalized,
    }


def audit_pilot(schedule_paths, trace_paths):
    """Return a deterministic reconciliation without consent-controlled fields."""
    diagnostics = []
    schedules = []
    for path in sorted(map(Path, schedule_paths), key=lambda item: item.name):
        try:
            schedules.append(_load_schedule(path))
        except ValueError:
            diagnostics.append(_diagnostic("invalid_schedule", source=path.name))

    planned = {}
    participants = set()
    manifest_identities = set()
    for schedule in schedules:
        participants.add(schedule["participant_id"])
        manifest_identities.add((schedule["study_id"], schedule["dataset_id"],
                                 schedule["manifest_version"], schedule["manifest_sha256"]))
        for trial in schedule["trials"]:
            key = (trial["participant_id"], trial["trial_id"])
            if key in planned:
                diagnostics.append(_diagnostic(
                    "duplicate_planned_trial", participant_id=key[0], trial_id=key[1]
                ))
            else:
                planned[key] = trial
    if len(manifest_identities) > 1:
        diagnostics.append(_diagnostic("mixed_schedule_manifests"))

    observed = defaultdict(list)
    practice_count = 0
    observed_formal_count = 0
    for path in sorted(map(Path, trace_paths), key=lambda item: item.name):
        try:
            analysis = analyze_path(path)
        except (OSError, ValueError, json.JSONDecodeError):
            diagnostics.append(_diagnostic("invalid_trace", source=path.name))
            continue
        if analysis.get("diagnostics"):
            diagnostics.append(_diagnostic(
                "trace_diagnostics", source=path.name,
                count=len(analysis["diagnostics"]),
            ))
        for session in analysis.get("trials", []):
            task_id = session.get("task_id")
            if isinstance(task_id, str) and task_id.startswith("practice-"):
                practice_count += 1
                continue
            observed_formal_count += 1
            participant_id, trial_id = session.get("participant_id"), session.get("trial_id")
            if not _text(participant_id) or not _text(trial_id):
                diagnostics.append(_diagnostic("incomplete_observed_context", source=path.name))
                continue
            observed[(participant_id, trial_id)].append({"source": path.name, **session})

    formal_rows = []
    complete_count = 0
    for key, plan in sorted(planned.items()):
        sessions = observed.pop(key, [])
        base = {
            "participant_id": plan["participant_id"],
            "trial_id": plan["trial_id"],
            "task_id": plan["task_id"],
            "condition": plan["condition"],
        }
        if not sessions:
            diagnostics.append(_diagnostic("missing_trial", **base))
            formal_rows.append({**base, "status": "missing"})
            continue
        if len(sessions) > 1:
            diagnostics.append(_diagnostic("duplicate_trial", count=len(sessions), **base))
            formal_rows.append({**base, "status": "duplicate", "observed_sessions": len(sessions)})
            continue
        session = sessions[0]
        mismatched = [field for field in ("task_id", "dataset_id", "condition")
                      if session.get(field) != plan[field]]
        if mismatched:
            diagnostics.append(_diagnostic(
                "context_mismatch", fields=mismatched, source=session["source"], **base
            ))
            formal_rows.append({**base, "status": "context_mismatch", "fields": mismatched})
            continue
        incomplete = False
        if session.get("diagnostics"):
            diagnostics.append(_diagnostic("trial_diagnostics", source=session["source"], **base))
            incomplete = True
        if session.get("duration_complete") is not True:
            diagnostics.append(_diagnostic("incomplete_trace", source=session["source"], **base))
            incomplete = True
        if session.get("request_count", 0) < 1:
            diagnostics.append(_diagnostic("no_accepted_request", source=session["source"], **base))
            incomplete = True
        if session.get("time_to_final_state_ms") is None:
            diagnostics.append(_diagnostic("no_final_state", source=session["source"], **base))
            incomplete = True
        status = "incomplete" if incomplete else "complete"
        if not incomplete:
            complete_count += 1
        formal_rows.append({
            **base,
            "status": status,
            "request_count": session.get("request_count"),
            "in_flight_revision_count": session.get("in_flight_revision_count"),
            "dashboard_commit_count": session.get("dashboard_commit_count"),
            "duration_ms": session.get("duration_ms"),
            "time_to_final_state_ms": session.get("time_to_final_state_ms"),
        })

    for (participant_id, trial_id), sessions in sorted(observed.items()):
        for session in sessions:
            diagnostics.append(_diagnostic(
                "unplanned_trial", participant_id=participant_id, trial_id=trial_id,
                task_id=session.get("task_id"), condition=session.get("condition"),
                source=session.get("source"),
            ))

    diagnostics.sort(key=lambda row: (
        row["code"], row.get("participant_id", ""), row.get("trial_id", ""), row.get("source", "")
    ))
    return {
        "schema_version": 1,
        "auditor_version": AUDITOR_VERSION,
        "summary": {
            "participant_count": len(participants),
            "planned_trial_count": len(planned),
            "observed_formal_session_count": observed_formal_count,
            "complete_trial_count": complete_count,
            "practice_session_count": practice_count,
            "diagnostic_count": len(diagnostics),
        },
        "trials": formal_rows,
        "diagnostics": diagnostics,
    }


def _files(path, suffix):
    path = Path(path)
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.glob(f"*{suffix}"))
    raise ValueError(f"path does not exist: {path}")


def _render(result):
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Reconcile generated VerbalVis pilot schedules with Trace v2 files."
    )
    parser.add_argument("--schedules", required=True, type=Path)
    parser.add_argument("--traces", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        schedule_paths = _files(args.schedules, ".json")
        trace_paths = _files(args.traces, ".jsonl")
        if not schedule_paths:
            raise ValueError("no schedule JSON files found")
        result = audit_pilot(schedule_paths, trace_paths)
        rendered = _render(result)
        if args.output:
            if args.output.exists():
                raise ValueError(f"output already exists: {args.output}")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 1 if args.strict and result["diagnostics"] else 0
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"audit_pilot: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
