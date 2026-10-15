"""Validate a study manifest and create one participant's trial URLs.

This utility deliberately does not randomize at run time.  The researcher
chooses one of the pre-registered sequence IDs so assignments can be audited
before and after a pilot without depending on hidden process state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

from refactor_next.backend.conditions import CANONICAL_CONDITIONS


_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
_MAX_TEXT = 2_000


def _token(value, field):
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ValueError(f"{field} must be a valid experiment token")
    return value


def _text(value, field):
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_TEXT:
        raise ValueError(f"{field} must be a non-empty bounded string")
    return value.strip()


def _validate_manifest(raw):
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    study_id = _token(raw.get("study_id"), "study_id")
    dataset_id = _token(raw.get("dataset_id"), "dataset_id")
    manifest_version = _token(raw.get("manifest_version"), "manifest_version")

    tasks_raw = raw.get("tasks")
    if not isinstance(tasks_raw, list) or len(tasks_raw) != 2:
        raise ValueError("pilot manifest must define exactly two study tasks")
    tasks = []
    task_ids = set()
    for index, task in enumerate(tasks_raw, start=1):
        if not isinstance(task, dict):
            raise ValueError(f"task {index} must be an object")
        task_id = _token(task.get("task_id"), f"task {index} task_id")
        if task_id in task_ids:
            raise ValueError("task_id values must be unique")
        task_ids.add(task_id)
        tasks.append({
            "task_id": task_id,
            "title": _text(task.get("title"), f"task {task_id} title"),
            "prompt": _text(task.get("prompt"), f"task {task_id} prompt"),
        })

    sequences_raw = raw.get("sequences")
    if not isinstance(sequences_raw, list) or len(sequences_raw) != 4:
        raise ValueError("two-task pilot manifest must define four counterbalanced sequences")
    sequence_ids = set()
    sequences = []
    for index, sequence in enumerate(sequences_raw, start=1):
        if not isinstance(sequence, dict):
            raise ValueError(f"sequence {index} must be an object")
        sequence_id = _token(sequence.get("sequence_id"), f"sequence {index} sequence_id")
        if sequence_id in sequence_ids:
            raise ValueError("sequence_id values must be unique")
        sequence_ids.add(sequence_id)
        trials_raw = sequence.get("trials")
        if not isinstance(trials_raw, list) or len(trials_raw) != len(tasks):
            raise ValueError(f"sequence {sequence_id} must use every study task once")
        trials = []
        for trial in trials_raw:
            if not isinstance(trial, dict):
                raise ValueError(f"sequence {sequence_id} trial must be an object")
            task_id = _token(trial.get("task_id"), f"sequence {sequence_id} task_id")
            if task_id not in task_ids:
                raise ValueError(f"sequence {sequence_id} references unknown task")
            condition = trial.get("condition")
            if not isinstance(condition, str) or condition not in CANONICAL_CONDITIONS:
                raise ValueError(f"sequence {sequence_id} must use a canonical condition")
            trials.append({"task_id": task_id, "condition": condition})
        if {trial["task_id"] for trial in trials} != task_ids:
            raise ValueError(f"sequence {sequence_id} must use every study task once")
        if {trial["condition"] for trial in trials} != set(CANONICAL_CONDITIONS):
            raise ValueError(f"sequence {sequence_id} must use both canonical conditions once")
        sequences.append({"sequence_id": sequence_id, "trials": trials})

    first_task_counts = Counter(sequence["trials"][0]["task_id"] for sequence in sequences)
    first_condition_counts = Counter(sequence["trials"][0]["condition"] for sequence in sequences)
    pairing_counts = Counter(
        (trial["task_id"], trial["condition"])
        for sequence in sequences
        for trial in sequence["trials"]
    )
    if (set(first_task_counts.values()) != {2} or
            set(first_condition_counts.values()) != {2} or
            set(pairing_counts.values()) != {2}):
        raise ValueError("pilot sequences must be counterbalanced by task, condition, and order")

    return {
        "schema_version": 1,
        "study_id": study_id,
        "dataset_id": dataset_id,
        "manifest_version": manifest_version,
        "tasks": tasks,
        "sequences": sequences,
    }


def load_manifest(path):
    """Read and fully validate a pilot manifest."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read pilot manifest: {exc}") from exc
    return _validate_manifest(raw)


def _base_url(value):
    if not isinstance(value, str):
        raise ValueError("base_url must be an HTTP(S) URL")
    parsed = urlsplit(value)
    try:
        hostname = parsed.hostname
        # Access performs urllib's numeric/range validation even though the
        # normalized URL keeps the original explicit port.
        parsed.port
    except ValueError as exc:
        raise ValueError("base_url contains an invalid port or host") from exc
    if (parsed.scheme not in {"http", "https"} or not parsed.netloc or not hostname or
            parsed.username is not None or parsed.password is not None or
            parsed.query or parsed.fragment):
        raise ValueError("base_url must be an HTTP(S) URL without credentials, query, or fragment")
    path = parsed.path or "/"
    if not path.endswith("/"):
        path += "/"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def build_schedule(manifest, *, participant_id, sequence_id, base_url):
    """Return a deterministic, serializable schedule for one participant."""
    manifest = _validate_manifest(deepcopy(manifest))
    manifest_sha256 = hashlib.sha256(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    participant_id = _token(participant_id, "participant_id")
    base_url = _base_url(base_url)
    sequence = next(
        (item for item in manifest["sequences"] if item["sequence_id"] == sequence_id),
        None,
    )
    if sequence is None:
        raise ValueError("sequence_id is not present in the manifest")
    task_by_id = {task["task_id"]: task for task in manifest["tasks"]}
    trials = []
    for index, assignment in enumerate(sequence["trials"], start=1):
        trial_id = _token(f"{participant_id}.t{index}", "trial_id")
        task = task_by_id[assignment["task_id"]]
        query = urlencode({
            "condition": assignment["condition"],
            "participant_id": participant_id,
            "trial_id": trial_id,
            "task_id": task["task_id"],
            "dataset_id": manifest["dataset_id"],
        })
        trials.append({
            "trial_index": index,
            "trial_id": trial_id,
            "task_id": task["task_id"],
            "condition": assignment["condition"],
            "title": task["title"],
            "prompt": task["prompt"],
            "url": f"{base_url}?{query}",
        })
    return {
        "schema_version": 1,
        "study_id": manifest["study_id"],
        "dataset_id": manifest["dataset_id"],
        "manifest_version": manifest["manifest_version"],
        "manifest_sha256": manifest_sha256,
        "participant_id": participant_id,
        "sequence_id": sequence["sequence_id"],
        "trials": trials,
    }


def _parser():
    parser = argparse.ArgumentParser(
        description="Create auditable VerbalVis pilot trial URLs from a validated manifest."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--participant-id", required=True)
    parser.add_argument("--sequence-id", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true", help="Replace an existing output file.")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        schedule = build_schedule(
            manifest,
            participant_id=args.participant_id,
            sequence_id=args.sequence_id,
            base_url=args.base_url,
        )
        rendered = json.dumps(schedule, ensure_ascii=False, indent=2) + "\n"
        if args.output is None:
            sys.stdout.write(rendered)
        else:
            if args.output.exists() and not args.force:
                raise ValueError(f"output already exists: {args.output}")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        return 0
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"prepare_pilot: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
