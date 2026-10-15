# Migration documentation hygiene refactor report

Date: 2026-10-15

## Scope completed

- Updated README.md, PILOT_RUNBOOK.md, OLIST_ADAPTER_REPORT.md, and archived migration records to use `datasets/olist/data/` as the repository-local Olist location.
- Added `datasets/olist/DATASET_SETUP.md` with the exact nine required filenames, the ignored directory policy, the non-distribution rule, and a neutral note to confirm applicable source terms.
- Stated the private-collaboration and no-public-release policy in README.md, with RELEASE_CHECKLIST.md as the canonical public-release gate.
- Preserved the existing frontend-design and research-system positioning in the project documentation.
- Removed machine-specific paths, former nested-checkout wording, and stale source-workspace status language from release-facing and archived migration documents. Archived plan/spec records now have an archive banner and omit machine locations.
- Added `.gitattributes` with LF text normalization; CSV and JSONL remain reviewable text, while audio and ZIP formats are binary.
- Added narrow ignored paths for experiment-local `data/`, `results/`, and `outputs/`, while retaining the existing ignore rules and marking the legacy local-data safeguard.
- Recorded the already-satisfied configuration-path ruling: relative explicit and environment configuration paths resolve from `ROOT`, with existing coverage for relative and absolute paths. No backend or test files were changed.

## Scan summary

Focused `rg` scans over Markdown, `.gitignore`, and `.gitattributes` found no machine-specific user or drive paths, former nested-frontend wording, obsolete parent-relative Olist paths, or parent-workspace terminology. This is a scoped documentation-and-metadata scan, not a claim about every file type or external system. A separate scan confirmed that Olist setup references point to `datasets/olist/data/`.

`git diff --check` completed without whitespace errors for the scoped changes.

## Unresolved items

- This hygiene work does not authorize publication, tagging, pushing, data distribution, licensing decisions, or research claims.
- Real Olist CSVs remain intentionally absent from the tracked tree and from repository distribution; data-backed smoke checks require a private local installation.
- Public-release, citation, licence, data-term, ethics, and real-provider validation gates remain in RELEASE_CHECKLIST.md.

## Follow-up correction wave

- README.md, PILOT_RUNBOOK.md, RELEASE_CHECKLIST.md, and the archived migration plan/spec now specify Python 3.11.14 and the locked installation sequence: `python -m pip install --require-hashes -r requirements.lock`, then `python -m pip install --no-deps -e .`.
- RELEASE_CHECKLIST.md and STUDY_FREEZE_CHECKLIST.md make the frontend working-directory transition explicit: `cd frontend` before npm commands and `cd ..` afterward.
- OLIST_ADAPTER_REPORT.md is labelled as migration-predecessor evidence and does not claim a current verification result; current final verification belongs in PROGRESS.md.
- SECURITY.md now prohibits public issue disclosure at this stage, requires an established private channel, and links the public-release gate.
- DESIGN_ZH.md is labelled as a historical design/audit baseline rather than a current implementation-path authority.
- Archived migration plan/spec links now use `datasets/olist/DATASET_SETUP.md`; the plan removes former nested-checkout wording.
