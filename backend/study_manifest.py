"""Validated manifests and deterministic between-subject study schedules."""

from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

from .conditions import CANONICAL_CONDITIONS


ALGORITHM_VERSION = "task-block-randomization-v1"
DEFAULT_SEED = 20261019
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_TASK_IDS = {"review-delivery-association", "freight-attribute-association"}
_CONSENT = {"transcript": "optional", "analysis_evidence": "required", "final_answer": "required"}
_LIMITS = {"exploration_limit_seconds": 600, "answer_limit_seconds": 180,
           "freeze_timeout_seconds": 15, "evidence_limit_bytes": 50 * 1024 * 1024,
           "answer_text_limit_chars": 8000}


def _token(value, field):
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ValueError(f"{field} must be a safe token")
    return value


def _text(value, field, limit=8_000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{field} must be non-empty bounded text")
    return value


def _sha256(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _canonical_hash(payload):
    stripped = {key: value for key, value in payload.items()
                if key not in {"manifest_sha256", "schedule_sha256"}}
    encoded = json.dumps(stripped, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_manifest(payload: dict) -> dict:
    """Return a normalized immutable-study manifest or raise ``ValueError``."""
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    if payload.get("design") != "between_subjects":
        raise ValueError("manifest design must be between_subjects")
    study_id = _token(payload.get("study_id"), "study_id")
    study_version = _token(payload.get("study_version"), "study_version")
    dataset_id = _token(payload.get("dataset_id"), "dataset_id")
    conditions = payload.get("conditions")
    if (not isinstance(conditions, list) or len(conditions) != 2 or
            set(conditions) != set(CANONICAL_CONDITIONS)):
        raise ValueError("conditions must be the two canonical conditions")
    if payload.get("limits") != _LIMITS:
        raise ValueError("limits must match the approved study limits")
    if payload.get("consent") != _CONSENT:
        raise ValueError("consent requirements must match the approved categories")
    source = payload.get("source_task_pool")
    if not isinstance(source, dict) or source.get("path") != "experiments/olist_study_task_pool.json":
        raise ValueError("source_task_pool path is invalid")
    source_hash = _sha256(source.get("sha256"), "source_task_pool sha256")
    tasks_raw = payload.get("tasks")
    if not isinstance(tasks_raw, list) or len(tasks_raw) != 2:
        raise ValueError("manifest must contain exactly two tasks")
    tasks = []
    for row in tasks_raw:
        if not isinstance(row, dict):
            raise ValueError("task must be an object")
        task_id = _token(row.get("task_id"), "task_id")
        title = _text(row.get("title"), f"task {task_id} title", 300)
        prompt = _text(row.get("prompt"), f"task {task_id} prompt")
        prompt_hash = _sha256(row.get("prompt_sha256"), f"task {task_id} prompt_sha256")
        if hashlib.sha256(prompt.encode("utf-8")).hexdigest() != prompt_hash:
            raise ValueError(f"task {task_id} prompt hash mismatch")
        tasks.append({"task_id": task_id, "title": title, "prompt": prompt,
                      "prompt_sha256": prompt_hash})
    if {row["task_id"] for row in tasks} != _TASK_IDS:
        raise ValueError("task set does not match approved task pool 2.0")
    return {
        "schema_version": 1, "design": "between_subjects", "study_id": study_id,
        "study_version": study_version, "dataset_id": dataset_id,
        "conditions": list(conditions), "limits": deepcopy(_LIMITS),
        "consent": deepcopy(_CONSENT),
        "source_task_pool": {"path": source["path"], "sha256": source_hash},
        "tasks": tasks,
    }


def prepare_cohort(manifest: dict, participant_ids: list[str], seed: int = DEFAULT_SEED) -> dict:
    """Assign twelve unique participants using task-block randomization."""
    manifest = validate_manifest(deepcopy(manifest))
    if (not isinstance(participant_ids, list) or len(participant_ids) != 12 or
            any(not isinstance(value, str) or not _TOKEN.fullmatch(value)
                for value in participant_ids) or len(set(participant_ids)) != 12):
        raise ValueError("participant_ids must contain 12 unique safe tokens")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    rng = random.Random(seed)
    shuffled = list(participant_ids)
    rng.shuffle(shuffled)
    task_ids = [row["task_id"] for row in manifest["tasks"]]
    manifest_sha256 = _canonical_hash(manifest)
    assignments = []
    for block_index, task_id in enumerate(task_ids):
        block = shuffled[block_index * 6:(block_index + 1) * 6]
        conditions = ["revision_enabled"] * 3 + ["turn_taking"] * 3
        rng.shuffle(conditions)
        for participant_id, condition in zip(block, conditions):
            assignment_id = f"{manifest['study_id']}.{participant_id}"
            _token(assignment_id, "assignment_id")
            assignments.append({
                "assignment_id": assignment_id,
                "participant_id": participant_id,
                "trial_id": f"{participant_id}.formal",
                "task_id": task_id,
                "condition": condition,
                "dataset_id": manifest["dataset_id"],
                "study_id": manifest["study_id"],
                "study_version": manifest["study_version"],
                "manifest_sha256": manifest_sha256,
                "is_practice": False,
            })
    assignments.sort(key=lambda row: row["participant_id"])
    cell_counts = Counter((row["task_id"], row["condition"]) for row in assignments)
    schedule = {
        "schema_version": 1, "algorithm_version": ALGORITHM_VERSION, "seed": seed,
        "python_version": sys.version.split()[0], "manifest_sha256": manifest_sha256,
        "study_id": manifest["study_id"], "study_version": manifest["study_version"],
        "dataset_id": manifest["dataset_id"], "tasks": deepcopy(manifest["tasks"]),
        "assignments": assignments,
        "balance": {
            "participants": 12,
            "conditions": dict(sorted(Counter(row["condition"] for row in assignments).items())),
            "tasks": dict(sorted(Counter(row["task_id"] for row in assignments).items())),
            "task_condition": {f"{task}|{condition}": count
                               for (task, condition), count in sorted(cell_counts.items())},
        },
    }
    schedule["schedule_sha256"] = _canonical_hash(schedule)
    return schedule


def _validate_schedule(payload):
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("invalid schedule schema")
    if payload.get("algorithm_version") != ALGORITHM_VERSION:
        raise ValueError("invalid schedule algorithm")
    tasks = payload.get("tasks")
    assignments = payload.get("assignments")
    if not isinstance(tasks, list) or {row.get("task_id") for row in tasks if isinstance(row, dict)} != _TASK_IDS:
        raise ValueError("invalid schedule tasks")
    if not isinstance(assignments, list) or len(assignments) != 12:
        raise ValueError("schedule must contain 12 assignments")
    if payload.get("schedule_sha256") != _canonical_hash(payload):
        raise ValueError("schedule hash mismatch")
    task_by_id = {}
    for task in tasks:
        prompt = task.get("prompt")
        if (not isinstance(prompt, str) or
                hashlib.sha256(prompt.encode("utf-8")).hexdigest() != task.get("prompt_sha256")):
            raise ValueError("schedule task hash mismatch")
        task_by_id[task["task_id"]] = deepcopy(task)
    normalized = []
    seen = set()
    participants = set()
    trials = set()
    for row in assignments:
        if not isinstance(row, dict) or set(row) != {
            "assignment_id", "participant_id", "trial_id", "task_id", "condition",
            "dataset_id", "study_id", "study_version", "manifest_sha256", "is_practice"
        }:
            raise ValueError("invalid schedule assignment shape")
        for field in ("assignment_id", "participant_id", "trial_id", "task_id", "dataset_id",
                      "study_id", "study_version"):
            _token(row.get(field), field)
        if row["condition"] not in CANONICAL_CONDITIONS or row["task_id"] not in task_by_id:
            raise ValueError("invalid schedule assignment context")
        if (row["is_practice"] is not False or row["manifest_sha256"] != payload.get("manifest_sha256") or
                row["dataset_id"] != payload.get("dataset_id") or
                row["study_id"] != payload.get("study_id") or
                row["study_version"] != payload.get("study_version")):
            raise ValueError("invalid schedule assignment identity")
        if row["assignment_id"] in seen:
            raise ValueError("duplicate assignment_id in schedule")
        if row["participant_id"] in participants:
            raise ValueError("duplicate participant in schedule")
        if row["trial_id"] in trials:
            raise ValueError("duplicate trial in schedule")
        seen.add(row["assignment_id"])
        participants.add(row["participant_id"])
        trials.add(row["trial_id"])
        normalized.append(deepcopy(row))
    condition_counts = Counter(row["condition"] for row in normalized)
    cell_counts = Counter((row["task_id"], row["condition"]) for row in normalized)
    if condition_counts != Counter({"revision_enabled": 6, "turn_taking": 6}):
        raise ValueError("invalid condition balance")
    if set(cell_counts) != {(task, condition) for task in _TASK_IDS
                           for condition in CANONICAL_CONDITIONS} or set(cell_counts.values()) != {3}:
        raise ValueError("invalid task-condition balance")
    return normalized, task_by_id


def load_assignment(schedule_dir: Path, assignment_id: str, dataset_id: str) -> dict:
    """Find an assignment by ID in validated schedules under one trusted directory."""
    schedule_dir = Path(schedule_dir)
    _token(assignment_id, "assignment_id")
    _token(dataset_id, "dataset_id")
    if not schedule_dir.is_dir():
        raise ValueError("schedule directory does not exist")
    matches = []
    for path in sorted(schedule_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            assignments, tasks = _validate_schedule(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid schedule file {path.name}: {exc}") from exc
        for row in assignments:
            if row["assignment_id"] == assignment_id:
                if row["dataset_id"] != dataset_id:
                    raise ValueError("assignment dataset does not match configured dataset")
                matches.append({**deepcopy(row), "task": deepcopy(tasks[row["task_id"]])})
    if len(matches) > 1:
        raise ValueError("duplicate assignment_id across schedules")
    if not matches:
        raise ValueError("unknown assignment_id")
    return matches[0]

