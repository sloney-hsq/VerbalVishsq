import hashlib
import json
import subprocess
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest

from backend.study_manifest import load_assignment, prepare_cohort, validate_manifest
from scripts.prepare_study import main


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments" / "olist_voice_policy_between_v1.json"


def test_balanced_single_trial_cohort_is_deterministic():
    manifest = validate_manifest(json.loads(MANIFEST.read_text(encoding="utf-8")))
    participants = [f"P{i:03d}" for i in range(1, 13)]
    schedule = prepare_cohort(manifest, participants, 20261019)

    assert schedule == prepare_cohort(manifest, participants, 20261019)
    assert schedule["algorithm_version"] == "task-block-randomization-v1"
    assert len(schedule["assignments"]) == 12
    assert Counter(row["participant_id"] for row in schedule["assignments"]) == {
        participant: 1 for participant in participants
    }
    assert Counter(row["condition"] for row in schedule["assignments"]) == {
        "revision_enabled": 6, "turn_taking": 6
    }
    assert set(Counter((row["task_id"], row["condition"])
                       for row in schedule["assignments"]).values()) == {3}
    assert all(row["is_practice"] is False for row in schedule["assignments"])
    assert all("attempt_id" not in row and "session_id" not in row
               for row in schedule["assignments"])
    assert schedule["balance"]["task_condition"] == {
        "freight-attribute-association|revision_enabled": 3,
        "freight-attribute-association|turn_taking": 3,
        "review-delivery-association|revision_enabled": 3,
        "review-delivery-association|turn_taking": 3,
    }


def test_manifest_uses_exact_pool_2_prompts_and_hashes():
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest = validate_manifest(raw)
    pool = json.loads((ROOT / "experiments/olist_study_task_pool.json").read_text(encoding="utf-8"))
    assert [(t["task_id"], t["title"], t["prompt"]) for t in manifest["tasks"]] == [
        (t["task_id"], t["title"], t["prompt"]) for t in pool["tasks"]
    ]
    for task in manifest["tasks"]:
        assert task["prompt_sha256"] == hashlib.sha256(task["prompt"].encode("utf-8")).hexdigest()


@pytest.mark.parametrize("participants", [
    ["P001"] * 12,
    [f"P{i:03d}" for i in range(13)],
])
def test_prepare_cohort_rejects_wrong_or_duplicate_participants(participants):
    manifest = validate_manifest(json.loads(MANIFEST.read_text(encoding="utf-8")))
    with pytest.raises(ValueError, match="12 unique"):
        prepare_cohort(manifest, participants, 1)


@pytest.mark.parametrize("mutation,error", [
    (lambda row: row.update(conditions=["revision_enabled", "full_duplex_rrt"]), "conditions"),
    (lambda row: row["tasks"].__setitem__(0, {**row["tasks"][0], "task_id": "unknown"}), "task"),
])
def test_manifest_rejects_noncanonical_conditions_and_unknown_tasks(mutation, error):
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    mutation(raw)
    with pytest.raises(ValueError, match=error):
        validate_manifest(raw)


def test_load_assignment_searches_validated_directory_without_path_join(tmp_path):
    manifest = validate_manifest(json.loads(MANIFEST.read_text(encoding="utf-8")))
    schedule = prepare_cohort(manifest, [f"P{i:03d}" for i in range(12)], 9)
    (tmp_path / "cohort.json").write_text(json.dumps(schedule), encoding="utf-8")
    wanted = schedule["assignments"][0]
    loaded = load_assignment(tmp_path, wanted["assignment_id"], "olist")
    assert {key: value for key, value in loaded.items() if key != "task"} == wanted
    assert loaded["task"]["task_id"] == wanted["task_id"]
    assert loaded["task"]["prompt"]
    with pytest.raises(ValueError, match="assignment_id"):
        load_assignment(tmp_path, "../cohort.json", "olist")
    with pytest.raises(ValueError, match="dataset"):
        load_assignment(tmp_path, wanted["assignment_id"], "education")
    duplicate = deepcopy(schedule)
    duplicate["assignments"] = [wanted]
    (tmp_path / "duplicate.json").write_text(json.dumps(duplicate), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_assignment(tmp_path, wanted["assignment_id"], "olist")


def test_load_assignment_rejects_rehashed_but_unbalanced_or_mixed_schedule(tmp_path):
    from backend.study_manifest import _canonical_hash
    manifest = validate_manifest(json.loads(MANIFEST.read_text(encoding="utf-8")))
    schedule = prepare_cohort(manifest, [f"P{i:03d}" for i in range(12)], 9)
    schedule["assignments"][1]["participant_id"] = schedule["assignments"][0]["participant_id"]
    schedule["assignments"][2]["condition"] = schedule["assignments"][0]["condition"]
    schedule["assignments"][3]["dataset_id"] = "education"
    schedule["schedule_sha256"] = _canonical_hash(schedule)
    (tmp_path / "bad.json").write_text(json.dumps(schedule), encoding="utf-8")
    with pytest.raises(ValueError, match="participant|balance|identity"):
        load_assignment(tmp_path, schedule["assignments"][0]["assignment_id"], "olist")


def test_prepare_study_cli_refuses_overwrite(tmp_path, capsys):
    output = tmp_path / "cohort.json"
    args = ["--manifest", str(MANIFEST), "--participants", "12", "--seed", "20261019",
            "--output", str(output)]
    assert main(args) == 0
    assert len(json.loads(output.read_text(encoding="utf-8"))["assignments"]) == 12
    assert main(args) == 2
    assert "already exists" in capsys.readouterr().err


def test_prepare_study_script_runs_from_clean_repo_cwd(tmp_path):
    output = tmp_path / "cohort.json"
    command = [sys.executable, "scripts/prepare_study.py", "--manifest", str(MANIFEST),
               "--participants", "12", "--seed", "20261019", "--output", str(output)]
    first = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    assert first.returncode == 0, first.stderr
    assert len(json.loads(output.read_text(encoding="utf-8"))["assignments"]) == 12
    second = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    assert second.returncode == 2
    assert "already exists" in second.stderr
