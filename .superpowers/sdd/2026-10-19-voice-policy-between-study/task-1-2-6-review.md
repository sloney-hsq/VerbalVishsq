# Read-only review — Tasks 1, 2, and 6

Reviewed `backend/study_manifest.py`, `backend/study_store.py`, `scripts/prepare_study.py`, `scripts/audit_study.py`, and `scripts/export_study.py` against the A/C runtime contract, persistence boundaries, and privacy constraints. No C-owned file was edited by A.

Outcome: no open blocking finding. The review-confirmed fixes are now present: every absent planned assignment produces `missing_assignment` so strict audit fails appropriately, and `trial.start` atomically sets `task_exposed` before any task-bearing server state can be sent. The manifest/schedule hash and 12-person balance checks, assignment-local ready evidence references, answer/client idempotency, consent-controlled transcript journal, controlled artifact paths and hash verification, blinded ratings export, and terminal-answer durability align with the approved design. C-focused verification passed `36 passed`; the integrated final Python suite passed `439 passed, 1 warning`.
