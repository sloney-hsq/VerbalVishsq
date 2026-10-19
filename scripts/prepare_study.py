"""Create one deterministic twelve-person between-subject study schedule."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.study_manifest import DEFAULT_SEED, prepare_cohort, validate_manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare the fixed VerbalVis voice-policy cohort.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--participants", required=True, type=int,
                        help="Number of generated pseudonymous IDs; must be 12.")
    parser.add_argument("--seed", default=DEFAULT_SEED, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.participants != 12:
            raise ValueError("participants must be exactly 12")
        manifest = validate_manifest(json.loads(args.manifest.read_text(encoding="utf-8")))
        source_path = (ROOT / manifest["source_task_pool"]["path"]).resolve()
        if ROOT not in source_path.parents or not source_path.is_file():
            raise ValueError("source task pool is outside the repository or missing")
        source_bytes = source_path.read_bytes()
        if hashlib.sha256(source_bytes).hexdigest() != manifest["source_task_pool"]["sha256"]:
            raise ValueError("source task pool hash mismatch")
        source_pool = json.loads(source_bytes.decode("utf-8"))
        source_tasks = [(row.get("task_id"), row.get("title"), row.get("prompt"))
                        for row in source_pool.get("tasks", [])]
        manifest_tasks = [(row["task_id"], row["title"], row["prompt"])
                          for row in manifest["tasks"]]
        if source_tasks != manifest_tasks:
            raise ValueError("manifest tasks do not exactly match task pool 2.0")
        schedule = prepare_cohort(manifest, [f"P{i:03d}" for i in range(1, 13)], args.seed)
        if args.output.exists():
            raise ValueError(f"output already exists: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(schedule, ensure_ascii=False, indent=2,
                                         sort_keys=True) + "\n", encoding="utf-8")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"prepare_study: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

