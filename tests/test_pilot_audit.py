import json
from pathlib import Path

from scripts.audit_pilot import audit_pilot, main
from scripts.prepare_pilot import build_schedule, load_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments" / "olist_pilot.json"


def _record(seq, event, *, session_id, participant_id, trial_id, task_id,
            condition, mono, correlation=None, data=None):
    return {
        "schema_version": 2,
        "seq": seq,
        "session_id": session_id,
        "participant_id": participant_id,
        "trial_id": trial_id,
        "task_id": task_id,
        "dataset_id": "olist",
        "condition": condition,
        "observed_at": f"2026-10-15T00:00:0{seq}+00:00",
        "monotonic_ns": mono,
        "event": event,
        "correlation": correlation or {},
        "data": data or {},
    }


def _write_trace(path, trial, *, session_id, task_id=None, condition=None,
                 close=True, request=True, private="DO NOT LEAK"):
    task_id = task_id or trial["task_id"]
    condition = condition or trial["condition"]
    common = {
        "session_id": session_id,
        "participant_id": "P001",
        "trial_id": trial["trial_id"],
        "task_id": task_id,
        "condition": condition,
    }
    rows = [_record(1, "session.started", mono=1_000_000_000, data={"transcript": private}, **common)]
    if request:
        rows.extend([
            _record(2, "user.request_received", mono=1_100_000_000,
                    correlation={"request_id": "r1"},
                    data={"received_at_monotonic_ns": 1_100_000_000}, **common),
            _record(3, "request.settled", mono=1_300_000_000,
                    correlation={"request_id": "r1"}, **common),
        ])
    if close:
        rows.append(_record(len(rows) + 1, "session.closed", mono=1_500_000_000, **common))
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def _schedule(tmp_path, sequence="S1"):
    schedule = build_schedule(
        load_manifest(MANIFEST), participant_id="P001", sequence_id=sequence,
        base_url="http://127.0.0.1:8001",
    )
    path = tmp_path / "P001.json"
    path.write_text(json.dumps(schedule), encoding="utf-8")
    return schedule, path


def test_audit_matches_complete_formal_trials_without_private_content(tmp_path):
    schedule, schedule_path = _schedule(tmp_path)
    traces = tmp_path / "traces"
    traces.mkdir()
    for index, trial in enumerate(schedule["trials"], start=1):
        _write_trace(traces / f"t{index}.jsonl", trial, session_id=f"session-{index}")

    result = audit_pilot([schedule_path], sorted(traces.glob("*.jsonl")))

    assert result["summary"] == {
        "participant_count": 1,
        "planned_trial_count": 2,
        "observed_formal_session_count": 2,
        "complete_trial_count": 2,
        "practice_session_count": 0,
        "diagnostic_count": 0,
    }
    assert [trial["status"] for trial in result["trials"]] == ["complete", "complete"]
    rendered = json.dumps(result)
    assert "DO NOT LEAK" not in rendered
    assert "prompt" not in rendered and "url" not in rendered


def test_audit_reports_missing_duplicate_mismatch_unplanned_and_practice(tmp_path):
    schedule, schedule_path = _schedule(tmp_path)
    traces = tmp_path / "traces"
    traces.mkdir()
    first, second = schedule["trials"]
    _write_trace(traces / "first-a.jsonl", first, session_id="s1")
    _write_trace(traces / "first-b.jsonl", first, session_id="s2")
    _write_trace(traces / "second.jsonl", second, session_id="s3", condition=first["condition"])
    practice = dict(first, trial_id="P001.p1", task_id="practice-turn")
    _write_trace(traces / "practice.jsonl", practice, session_id="practice")
    unplanned = dict(first, trial_id="P001.t9")
    _write_trace(traces / "unplanned.jsonl", unplanned, session_id="unplanned")

    result = audit_pilot([schedule_path], sorted(traces.glob("*.jsonl")))
    codes = {item["code"] for item in result["diagnostics"]}

    assert {"duplicate_trial", "context_mismatch", "unplanned_trial"} <= codes
    assert result["summary"]["practice_session_count"] == 1
    assert result["summary"]["complete_trial_count"] == 0
    assert {trial["status"] for trial in result["trials"]} == {"duplicate", "context_mismatch"}


def test_audit_requires_complete_trace_request_and_terminal_state(tmp_path):
    schedule, schedule_path = _schedule(tmp_path)
    traces = tmp_path / "traces"
    traces.mkdir()
    first, second = schedule["trials"]
    _write_trace(traces / "first.jsonl", first, session_id="s1", close=False)
    _write_trace(traces / "second.jsonl", second, session_id="s2", request=False)

    result = audit_pilot([schedule_path], sorted(traces.glob("*.jsonl")))
    codes = {item["code"] for item in result["diagnostics"]}

    assert {"incomplete_trace", "no_accepted_request", "no_final_state"} <= codes
    assert result["summary"]["complete_trial_count"] == 0


def test_cli_discovers_directories_writes_report_and_strict_fails_on_gap(tmp_path, capsys):
    schedule, _ = _schedule(tmp_path)
    schedule_dir = tmp_path / "schedules"
    schedule_dir.mkdir()
    (schedule_dir / "P001.json").write_text(json.dumps(schedule), encoding="utf-8")
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    _write_trace(trace_dir / "first.jsonl", schedule["trials"][0], session_id="s1")
    output = tmp_path / "audit.json"

    assert main([
        "--schedules", str(schedule_dir), "--traces", str(trace_dir),
        "--output", str(output), "--strict",
    ]) == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["summary"]["planned_trial_count"] == 2
    assert any(item["code"] == "missing_trial" for item in report["diagnostics"])
    assert "missing_trial" not in capsys.readouterr().out
