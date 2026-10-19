#!/usr/bin/env python3
"""Create separate whitelisted technical, blinded-rating, or process packages."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.study_store import StudyStore


PACKAGES = {"technical", "ratings", "process"}


def _artifact_source(root, evidence, attempt_id, revision):
    if (evidence is None or evidence.get("attempt_id") != attempt_id or
            evidence.get("revision") != revision or evidence.get("status") != "ready"):
        raise ValueError("evidence reference is not ready or belongs to another attempt")
    relative = evidence.get("relative_path")
    if not isinstance(relative, str):
        raise ValueError("evidence path is missing")
    source = (root / relative).resolve()
    artifact_root = (root / "artifacts").resolve()
    if artifact_root not in source.parents or not source.is_file():
        raise ValueError("evidence path escapes the controlled artifact directory")
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != evidence.get("sha256"):
        raise ValueError("evidence hash mismatch")
    return source


def _write_json(path, payload):
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                    sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def export_study(study_root: Path, output_dir: Path, *, package: str) -> dict:
    """Export one safe package and refuse any overwrite."""
    if package not in PACKAGES:
        raise ValueError("package must be technical, ratings, or process")
    study_root = Path(study_root).resolve()
    output_dir = Path(output_dir).resolve()
    if not study_root.is_dir() or not (study_root / "study.sqlite3").is_file():
        raise ValueError(f"study database does not exist: {study_root}")
    if output_dir.exists():
        raise ValueError(f"output directory already exists: {output_dir}")
    if study_root == output_dir or study_root in output_dir.parents:
        raise ValueError("output directory must be outside study data")
    store = StudyStore(study_root)
    attempts = {row["attempt_id"]: row for row in store.list_attempts()}
    answers = store.list_answers()
    evidence = {row["artifact_id"]: row for row in store.list_evidence()}
    events = store.list_events()
    questionnaires = {row["attempt_id"]: row["responses"] for row in store.list_questionnaires()}
    artifact_copies = []

    if package == "ratings":
        records = []
        for answer in answers:
            attempt = attempts[answer["attempt_id"]]
            blinded_id = "rating-" + hashlib.sha256(answer["attempt_id"].encode("utf-8")).hexdigest()[:16]
            exported_refs = []
            for ref in answer["evidence_refs"]:
                source = _artifact_source(study_root, evidence.get(ref["artifact_id"]),
                                          answer["attempt_id"], ref["revision"])
                filename = f"{blinded_id}-revision-{ref['revision']}.json"
                artifact_copies.append((source, filename))
                exported_refs.append({"revision": ref["revision"], "file": f"artifacts/{filename}"})
            records.append({
                "rating_id": blinded_id, "task_id": attempt["task_id"],
                "answer_status": answer["answer_status"], "conclusion": answer["conclusion"],
                "evidence_refs": exported_refs, "limitations": answer["limitations"],
            })
    elif package == "process":
        event_by_attempt = {}
        for attempt_id, attempt in attempts.items():
            allowed_events = []
            for row in events:
                if row["attempt_id"] != attempt_id:
                    continue
                metadata = {key: value for key, value in row["metadata"].items()
                            if key in {"request_id", "classification", "transcript", "reason_code",
                                       "dashboard_revision", "status", "error_code"}}
                if not attempt["consent"]["transcript"]:
                    metadata.pop("transcript", None)
                allowed_events.append({"seq": row["seq"], "event": row["event"], "metadata": metadata})
            event_by_attempt[attempt_id] = allowed_events
        records = [{
            "attempt_id": row["attempt_id"], "participant_id": row["participant_id"],
            "task_id": row["task_id"], "condition": row["condition"],
            "phase": row["phase"], "events": event_by_attempt[row["attempt_id"]],
            "questionnaire": questionnaires.get(row["attempt_id"]),
            "transcript_authorized": row["consent"]["transcript"],
        } for row in attempts.values()]
    else:
        evidence_by_attempt = {}
        for row in evidence.values():
            evidence_by_attempt.setdefault(row["attempt_id"], []).append({
                "artifact_id": row["artifact_id"], "revision": row["revision"],
                "status": row["status"], "byte_count": row["byte_count"],
                "sha256": row["sha256"], "error_code": row["error_code"],
            })
        records = [{
            "attempt_id": row["attempt_id"], "assignment_id": row["assignment_id"],
            "session_id": row["session_id"], "task_id": row["task_id"],
            "condition": row["condition"], "phase": row["phase"], "status": row["status"],
            "task_exposed": row["task_exposed"], "freeze_status": row["freeze_status"],
            "frozen_revision": row["frozen_revision"],
            "last_rendered_revision": row["last_rendered_revision"],
            "evidence_failure": row["evidence_failure"], "provenance": row["provenance"],
            "evidence": sorted(evidence_by_attempt.get(row["attempt_id"], []),
                               key=lambda item: item["revision"]),
        } for row in attempts.values()]

    payload = {"schema_version": 1, "package": package, "records": records}
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.with_name(f".{output_dir.name}.{uuid.uuid4().hex}.tmp")
    try:
        staging.mkdir()
        if artifact_copies:
            artifact_dir = staging / "artifacts"
            artifact_dir.mkdir()
            for source, filename in artifact_copies:
                temporary = artifact_dir / f".{filename}.{uuid.uuid4().hex}.tmp"
                shutil.copyfile(source, temporary)
                os.replace(temporary, artifact_dir / filename)
        _write_json(staging / f"{package}.json", payload)
        os.replace(staging, output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {"schema_version": 1, "package": package, "record_count": len(records),
            "artifact_count": len(artifact_copies), "output_dir": str(output_dir)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export a safe VerbalVis study package.")
    parser.add_argument("--study-data", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--package", required=True, choices=sorted(PACKAGES))
    args = parser.parse_args(argv)
    try:
        result = export_study(args.study_data, args.output, package=args.package)
        sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
        return 0
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"export_study: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
