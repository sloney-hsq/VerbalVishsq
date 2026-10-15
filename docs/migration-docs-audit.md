# Standalone release and migration documentation audit

Audit date: 2026-10-15  
Scope: release/migration-facing text and repository metadata. This audit is an edit plan, not a release authorization.

## Resolved documentation contract

- Olist setup names `datasets/olist/data/` as the only repository-local data directory. It is Git-ignored and the repository does not distribute the CSV files.
- README.md states that the repository is for private collaboration and that public release requires every item in RELEASE_CHECKLIST.md.
- README.md and PILOT_RUNBOOK.md define repository-root command context and the one `cd frontend` exception.
- Historical migration records are labelled as archived, use no machine-specific locations, and refer only to an approved source snapshot or unrelated source history.
- Historical verification reports use repository-relative commands and do not present unrelated workspace state as current repository status.
- DATASET_SETUP.md names the required Olist CSV files, their directory, Git-ignore policy, and non-distribution rule without asserting a licence conclusion.
- `.gitattributes` enforces LF for text while leaving CSV and JSONL reviewable; audio and archive formats are binary.
- `.gitignore` retains existing rules and adds narrow ignored experiment data, results, and outputs directories.

## Technical ruling

The configuration-path recommendation in the original audit is already satisfied: `backend/main.py` resolves relative explicit and environment configuration paths from `ROOT`, while preserving absolute paths. Existing application tests cover relative environment configuration, relative explicit configuration, and absolute configuration. No additional code or test change is requested by this document.

## Release gate

These changes improve repository hygiene only. They do not authorize publishing, tagging, pushing, data distribution, or a claim of provider or user-study validation. Consult README.md and RELEASE_CHECKLIST.md before any public action.
