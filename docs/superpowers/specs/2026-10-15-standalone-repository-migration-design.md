# VerbalVis Standalone Repository Migration Design

## Goal

Move the paper-facing implementation from
`F:\VerbalVis2 - 副本 (4)7月15\refactor_next` into a clean standalone
repository at `C:\verbalvis`. The source
directory remains unchanged until the destination passes every acceptance
check.

## Migration boundary

The migration copies the current application, tests, research utilities and
documentation. It does not copy the parent repository history because
`refactor_next` is currently an untracked subtree of a dirty parent repository;
that history cannot accurately describe this implementation.

The migration and the paper runtime refactor are two separate changes. The
standalone repository first receives a behavior-preserving baseline. The
`execution.py` extraction and versioned RRT commit path begin from a new branch
after that baseline is verified.

## Included content

- `.github/workflows/ci.yml`
- `backend/`, excluding caches and local Olist data
- `configs/`
- `datasets/`, excluding copied real Olist data
- `experiments/`
- `frontend/index.html`, package manifests, Vite configuration, `src/` and
  `tests/`
- `scripts/`
- `tests/`, including the small synthetic Trace fixture
- Python packaging and dependency manifests
- README, architecture, validation, pilot, coding, security and release
  documentation

## Excluded content

- Parent `.git` history and all parent-project files
- `.superpowers/` snapshots and implementation scratch state
- `.env` and credentials
- `node_modules/`, `dist/`, caches, bytecode and editable-install metadata
- `traces/`, `pilot_sessions/`, `participant_data/` and `raw_audio/`
- Real Olist CSV files
- Local shortcuts and editor configuration
- The parent-level `refactor_next.zip`

## Standalone path contract

All shipped paths resolve from the new repository root. The bundled Education
dataset remains at `datasets/education/data.csv`. The local Olist installation
location becomes `datasets/olist/data/`, which is ignored by Git and keeps
dataset-owned data with its adapter.
`configs/olist.json` must not refer to `..` or any old project directory.

`VERBALVIS_CONFIG` may be absolute or repository-root relative. Starting the
application from another current working directory must still resolve a
relative config against the installed repository root. Trace paths remain
repository-root relative unless an absolute path is explicitly configured.

## Repository identity

The first standalone baseline preserves the current Python import/package
identity and application commands. Package renaming and source-layout changes
are deferred to a separate reviewed change so migration failures cannot be
confused with architecture changes.

The new repository begins with a single baseline commit after clean-environment
verification. A local baseline tag identifies the exact pre-refactor state.
The verified baseline is pushed to a newly created private GitHub repository;
public release remains a separate decision gated by licensing, citation, data
distribution and research-ethics review.

The initial standalone repository remains a source-checkout application:
editable Python installation, frontend build and repository-root execution are
the supported workflow. Wheel/container packaging and Python package renaming
are explicitly deferred.

## Local research data

The repository contains no real Olist data, credentials or participant data.
Researchers copy Olist CSVs to the ignored `datasets/olist/data/` directory, or
use a private absolute path in a local configuration that is itself ignored.
Migration records the exact nine source filenames and SHA-256 values before a
private local copy is made; those files are never staged or pushed.
Formal-study Trace, schedules and consent-controlled artifacts remain ignored
and outside release archives.

## Acceptance criteria

1. The destination contains no file from the exclusion list.
2. A scan finds no old absolute project path or credential value.
3. `python -m pip install -e .` succeeds in a fresh Python 3.11 environment.
4. `python -m pytest tests -q` passes.
5. `npm ci`, `npm test` and `npm run build` pass under Node 20.
6. The Education configuration starts without real Olist data.
7. An explicit data preflight verifies all nine Olist filenames and checksums;
   adapter and initial-dashboard checks pass after local CSVs are placed in
   `datasets/olist/data/`.
8. Pilot schedule generation and strict Trace fixture analysis pass.
9. `git status` is clean after the baseline commit, and ignored research data
   remains untracked.
10. The original source directory remains available until the standalone
    baseline has been reviewed.
11. A fresh private GitHub repository contains the verified `main` branch and
    no ignored data, credentials, generated output or parent-repository history.

## Rollback

Migration uses copy, not move. A failed destination can be abandoned without
changing the source tree. The source is retired only after the destination has
passed all acceptance criteria and the user has confirmed the new location.
