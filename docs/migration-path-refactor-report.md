# Standalone Path Refactor Report

Date: 2026-10-15  
Repository: standalone repository root
Plan scope: Task 3 of `docs/superpowers/plans/2026-10-15-standalone-repository-migration.md`

## Result

- `configs/olist.json` now uses the repository-local, Git-ignored Olist directory: `datasets/olist/data`.
- `read_config(config=None)` resolves relative explicit config paths and relative `VERBALVIS_CONFIG` values from the repository `ROOT`.
- Absolute `VERBALVIS_CONFIG` paths retain their existing behavior and are not prefixed with `ROOT`.
- The missing-frontend-build response instructs users to run the build in `frontend`; it no longer uses former nested-checkout wording.
- No paper protocol, frontend behavior, or UI code was changed.

This historical report records only the completed path-contract work; later documentation hygiene is recorded separately. At the time of this refactor, no standalone baseline commit had been created. Consult Git history for the current repository state.

## TDD evidence

The Windows Store `python.exe` alias initially returned exit code 9009 without running pytest. That attempt is not counted as RED evidence. All valid runs below used the repository virtual environment (Python 3.11.14, pytest 9.1.1).

### Cycle 1: repository-local Olist data path

RED command:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/test_initial_dashboard.py::test_olist_config_uses_ignored_repo_local_data_directory -q
```

RED output summary:

```text
FAILED tests/test_initial_dashboard.py::test_olist_config_uses_ignored_repo_local_data_directory
AssertionError: the configured data directory did not equal the repository-local ignored Olist directory
1 failed in 0.36s
```

Minimal implementation: changed `dataset.data_dir` in `configs/olist.json` to `datasets/olist/data`.

GREEN command:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/test_initial_dashboard.py::test_olist_config_uses_ignored_repo_local_data_directory tests/test_olist_adapter.py -q
```

GREEN output summary:

```text
25 passed in 4.11s
```

### Cycle 2: repository-root config resolution

RED command for environment configuration:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/test_app.py::test_relative_env_config_resolves_from_repository_root tests/test_app.py::test_absolute_env_config_path_is_preserved -q
```

RED output summary:

```text
FAILED tests/test_app.py::test_relative_env_config_resolves_from_repository_root
FileNotFoundError: [Errno 2] No such file or directory: 'configs\\education.json'
1 failed, 1 passed, 1 warning in 1.55s
```

The passing test is a characterization guard proving that the pre-existing absolute-path behavior remained intact.

RED command for an explicitly supplied relative config:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/test_app.py::test_relative_explicit_config_resolves_from_repository_root -q
```

RED output summary:

```text
FAILED tests/test_app.py::test_relative_explicit_config_resolves_from_repository_root
FileNotFoundError: [Errno 2] No such file or directory: 'configs\\education.json'
1 failed, 1 warning in 1.18s
```

Minimal implementation: convert the selected config to `Path` and prepend `ROOT` only when `path.is_absolute()` is false.

GREEN command:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/test_app.py::test_relative_env_config_resolves_from_repository_root tests/test_app.py::test_relative_explicit_config_resolves_from_repository_root tests/test_app.py::test_absolute_env_config_path_is_preserved -q
```

GREEN output summary:

```text
3 passed, 1 warning in 0.59s
```

### Cycle 3: standalone missing-build hint

RED command:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/test_app.py::test_missing_frontend_build_hint_uses_standalone_repository_path -q
```

RED output summary:

```text
FAILED tests/test_app.py::test_missing_frontend_build_hint_uses_standalone_repository_path
AssertionError: the response still contained former nested-checkout wording
1 failed, 1 warning in 0.63s
```

Minimal implementation: changed the response text to name `frontend`.

GREEN command:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/test_app.py::test_missing_frontend_build_hint_uses_standalone_repository_path -q
```

GREEN output summary:

```text
1 passed, 1 warning in 0.46s
```

During self-review, this test was isolated from a future real `frontend/dist` directory by monkeypatching `ROOT` to `tmp_path`. The focused test was rerun after that test-only hardening:

```text
1 passed, 1 warning in 0.54s
```

## Regression verification

Task-focused regression command:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/test_app.py tests/test_initial_dashboard.py tests/test_olist_adapter.py -q
```

Output summary:

```text
51 passed, 1 warning in 8.25s
```

Fresh full-suite command after the final test hardening and report creation:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests -q
```

Output summary:

```text
301 passed, 1 warning in 11.34s
```

Contract checks also confirmed:

```text
olist.data_dir=datasets/olist/data
has_parent_segment=False
stale_hint=absent
```

## Changed files

- `configs/olist.json`
- `backend/main.py`
- `tests/test_app.py`
- `tests/test_initial_dashboard.py`
- `docs/migration-path-refactor-report.md`

## Review and residual risk

Self-review found no Critical, Important, or deferred Minor code findings after hardening the missing-build test against a pre-existing `frontend/dist` directory.

Residual risks:

- Every FastAPI test run emits one existing `StarletteDeprecationWarning` about the `httpx` compatibility shim. It does not fail the suite and is outside this path-refactor scope.
- Real Olist CSVs are intentionally absent from the repository, so data-backed Olist smoke coverage remains conditional on a private local dataset installation. The adapter's synthetic suite passed.
- This task did not run frontend tests or a frontend build because no frontend code or behavior changed; the standalone migration's later clean-environment task owns those checks.
- Because this is an unborn repository with no baseline commit, Git cannot provide a meaningful pre/post diff for this task. Verification relied on observed RED/GREEN test output, scoped file inspection, and the full Python suite.
