from collections import Counter
import json
import subprocess
import sys
from pathlib import Path

from scripts.audit_study import audit_assignments
from backend.study_store import StudyStore


ROOT = Path(__file__).resolve().parents[1]


def schedule():
    assignments = []
    tasks = ["review-delivery-association", "freight-attribute-association"]
    for index in range(12):
        task = tasks[index // 6]
        condition = "revision_enabled" if index % 6 < 3 else "turn_taking"
        assignments.append({
            "assignment_id": f"A{index:02d}", "participant_id": f"P{index:02d}",
            "trial_id": f"T{index:02d}", "task_id": task, "condition": condition,
            "dataset_id": "olist", "study_id": "study", "study_version": "1",
            "manifest_sha256": "a" * 64, "is_practice": False,
        })
    return {"schema_version": 1, "assignments": assignments}


def attempt(plan, attempt_id, phase, *, exposed=False, answer_status=None, condition=None,
            session_id=None, is_practice=False):
    return {
        **plan, "attempt_id": attempt_id, "phase": phase, "task_exposed": exposed,
        "answer_status": answer_status, "condition": condition or plan["condition"],
        "session_id": session_id or f"S-{attempt_id}", "is_practice": is_practice,
    }


def test_audit_counts_assignments_not_attempts_and_distinguishes_empty():
    cohort = schedule()
    rows = cohort["assignments"]
    attempts = [
        attempt(rows[0], "old", "aborted", exposed=True),
        attempt(rows[0], "retry", "completed", exposed=True, answer_status="submitted"),
        attempt(rows[1], "empty", "completed", exposed=True, answer_status="empty"),
        attempt(rows[2], "aborted", "aborted", exposed=False),
        attempt(rows[3], "wrong-condition", "completed", exposed=True,
                answer_status="submitted", condition="revision_enabled"),
        attempt({**rows[4], "assignment_id": "unplanned", "task_id": rows[5]["task_id"]},
                "second-task", "completed", exposed=True, answer_status="submitted"),
        attempt({**rows[5], "assignment_id": "practice"}, "practice", "completed",
                is_practice=True),
    ]
    traces = [
        {"session_id": "S-empty", "participant_id": rows[1]["participant_id"],
         "trial_id": rows[1]["trial_id"], "task_id": rows[1]["task_id"],
         "condition": rows[1]["condition"]},
    ]
    result = audit_assignments(cohort, attempts, traces)

    assert result["planned"] == 12
    assert result["started"] == 4  # assignment denominator, retries do not add one
    assert result["completed"] == 1  # valid empty is still completed
    assert result["aborted"] == 1
    assert result["missing"] == 8
    assert result["practice_attempts"] == 1
    codes = Counter(row["code"] for row in result["diagnostics"])
    assert codes["retry_after_exposure"] == 1
    assert codes["condition_mismatch"] == 1
    assert codes["second_formal_task"] >= 1
    assert codes["unplanned_attempt"] == 1
    assert next(row for row in result["assignments"] if row["assignment_id"] == rows[1]["assignment_id"])["answer_status"] == "empty"


def test_audit_reports_actual_unbalanced_schedule_without_padding():
    cohort = schedule()
    cohort["assignments"] = cohort["assignments"][:-1]
    result = audit_assignments(cohort, [], [])
    assert result["planned"] == 11
    assert result["missing"] == 11
    assert any(row["code"] == "planned_count" and row["actual"] == 11
               for row in result["diagnostics"])


def test_audit_reports_each_missing_assignment_without_changing_denominator():
    result = audit_assignments(schedule(), [], [])

    missing = [row for row in result["diagnostics"]
               if row["code"] == "missing_assignment"]
    assert result["planned"] == 12
    assert result["started"] == 0
    assert result["missing"] == 12
    assert len(missing) == 12
    assert {row["assignment_id"] for row in missing} == {
        row["assignment_id"] for row in schedule()["assignments"]
    }


def test_retry_order_uses_created_time_not_random_attempt_id():
    cohort = schedule()
    plan = cohort["assignments"][0]
    old = {**attempt(plan, "z-old", "aborted", exposed=True), "created_ns": 10}
    retry = {**attempt(plan, "a-new", "completed", exposed=False, answer_status="submitted"),
             "created_ns": 20}
    result = audit_assignments(cohort, [retry, old], [])
    assert any(row["code"] == "retry_after_exposure" for row in result["diagnostics"])
    assert result["completed"] == 0


def test_audit_script_runs_from_clean_repo_cwd(tmp_path):
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text(json.dumps(schedule()), encoding="utf-8")
    StudyStore(tmp_path / "study-data")
    command = [sys.executable, "scripts/audit_study.py", "--schedule", str(schedule_path),
               "--study-data", str(tmp_path / "study-data"), "--output", str(tmp_path / "audit.json")]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path / "audit.json").read_text(encoding="utf-8"))["planned"] == 12


def test_audit_script_strict_rejects_valid_schedule_with_no_started_assignments(tmp_path):
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text(json.dumps(schedule()), encoding="utf-8")
    StudyStore(tmp_path / "study-data")
    output = tmp_path / "audit.json"

    result = subprocess.run(
        [sys.executable, "scripts/audit_study.py", "--schedule", str(schedule_path),
         "--study-data", str(tmp_path / "study-data"), "--output", str(output),
         "--strict"], cwd=ROOT, text=True, capture_output=True, check=False)

    assert result.returncode == 1, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["missing"] == 12
    assert sum(row["code"] == "missing_assignment"
               for row in report["diagnostics"]) == 12


def test_audit_script_rejects_missing_study_database_without_creating_it(tmp_path):
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text(json.dumps(schedule()), encoding="utf-8")
    missing = tmp_path / "missing"
    result = subprocess.run(
        [sys.executable, "scripts/audit_study.py", "--schedule", str(schedule_path),
         "--study-data", str(missing)], cwd=ROOT, text=True, capture_output=True, check=False)
    assert result.returncode == 2
    assert "study database" in result.stderr
    assert not missing.exists()
