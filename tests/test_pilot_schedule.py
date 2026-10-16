import json
import re
from copy import deepcopy
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from scripts.prepare_pilot import build_schedule, load_manifest, main


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments" / "olist_pilot.json"


def test_olist_pilot_manifest_is_balanced_and_uses_canonical_conditions():
    manifest = load_manifest(MANIFEST)

    assert manifest["dataset_id"] == "olist"
    assert len(manifest["tasks"]) == 2
    assert len(manifest["sequences"]) == 4

    task_ids = {task["task_id"] for task in manifest["tasks"]}
    first_conditions = []
    first_tasks = []
    pair_counts = {}
    for sequence in manifest["sequences"]:
        trials = sequence["trials"]
        assert {trial["condition"] for trial in trials} == {
            "turn_taking", "revision_enabled"
        }
        assert {trial["task_id"] for trial in trials} == task_ids
        first_conditions.append(trials[0]["condition"])
        first_tasks.append(trials[0]["task_id"])
        for trial in trials:
            key = (trial["task_id"], trial["condition"])
            pair_counts[key] = pair_counts.get(key, 0) + 1

    assert first_conditions.count("turn_taking") == 2
    assert first_conditions.count("revision_enabled") == 2
    assert all(first_tasks.count(task_id) == 2 for task_id in task_ids)
    assert set(pair_counts.values()) == {2}


def test_schedule_urls_round_trip_only_valid_experiment_context():
    manifest = load_manifest(MANIFEST)
    schedule = build_schedule(
        manifest,
        participant_id="P-007",
        sequence_id="S3",
        base_url="http://127.0.0.1:8001/",
    )

    assert schedule["participant_id"] == "P-007"
    assert schedule["sequence_id"] == "S3"
    assert schedule["manifest_version"] == "1.1"
    assert re.fullmatch(r"[0-9a-f]{64}", schedule["manifest_sha256"])
    assert len(schedule["trials"]) == 2
    for index, trial in enumerate(schedule["trials"], start=1):
        parsed = urlparse(trial["url"])
        query = parse_qs(parsed.query)
        assert parsed.scheme == "http" and parsed.netloc == "127.0.0.1:8001"
        assert query == {
            "condition": [trial["condition"]],
            "participant_id": ["P-007"],
            "trial_id": [f"P-007.t{index}"],
            "task_id": [trial["task_id"]],
            "dataset_id": ["olist"],
        }
        assert trial["prompt"] not in trial["url"]

    changed = deepcopy(manifest)
    changed["tasks"][0]["prompt"] += " Updated."
    changed_schedule = build_schedule(
        changed,
        participant_id="P-007",
        sequence_id="S3",
        base_url="http://127.0.0.1:8001/",
    )
    assert changed_schedule["manifest_sha256"] != schedule["manifest_sha256"]


@pytest.mark.parametrize(
    "participant,sequence,base_url,error",
    [
        ("bad token", "S1", "http://127.0.0.1:8001", "participant_id"),
        ("P1", "unknown", "http://127.0.0.1:8001", "sequence_id"),
        ("P1", "S1", "file:///tmp/demo", "base_url"),
        ("P1", "S1", "http://127.0.0.1:8001/?condition=x", "base_url"),
        ("P1", "S1", "http://:8001", "base_url"),
        ("P1", "S1", "http://127.0.0.1:not-a-port", "base_url"),
        ("P1", "S1", "http://127.0.0.1:999999", "base_url"),
    ],
)
def test_schedule_rejects_ambiguous_or_unsafe_inputs(participant, sequence, base_url, error):
    manifest = load_manifest(MANIFEST)
    with pytest.raises(ValueError, match=error):
        build_schedule(
            manifest,
            participant_id=participant,
            sequence_id=sequence,
            base_url=base_url,
        )


def test_cli_writes_valid_schedule_and_refuses_accidental_overwrite(tmp_path, capsys):
    output = tmp_path / "P001.json"
    arguments = [
        "--manifest", str(MANIFEST),
        "--participant-id", "P001",
        "--sequence-id", "S1",
        "--base-url", "http://127.0.0.1:8001",
        "--output", str(output),
    ]

    assert main(arguments) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["participant_id"] == "P001"
    assert main(arguments) == 2
    assert "already exists" in capsys.readouterr().err


def test_manifest_rejects_unknown_task_and_noncanonical_condition(tmp_path):
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw["sequences"][0]["trials"][0]["task_id"] = "missing"
    raw["sequences"][0]["trials"][0]["condition"] = "full_duplex_rrt"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="canonical condition|unknown task"):
        load_manifest(path)


def test_manifest_rejects_unbalanced_but_individually_valid_sequences(tmp_path):
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw["sequences"][3]["trials"] = raw["sequences"][0]["trials"]
    path = tmp_path / "unbalanced.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="counterbalanced"):
        load_manifest(path)


@pytest.mark.parametrize("field", ["task_id", "condition"])
def test_manifest_rejects_non_scalar_trial_fields_without_type_error(tmp_path, field):
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw["sequences"][0]["trials"][0][field] = []
    path = tmp_path / f"invalid-{field}.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match=field):
        load_manifest(path)
