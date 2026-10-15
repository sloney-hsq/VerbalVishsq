# VerbalVis Standalone Repository Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a clean standalone VerbalVis research repository that reproduces the current tested behavior and is ready for the paper runtime refactor.

**Architecture:** Export the approved subtree through an explicit allowlist, harden repository-root path resolution, rebuild dependencies in clean environments, then establish a verified baseline commit. Runtime architecture changes begin only after migration is complete.

**Tech Stack:** Python 3.11, FastAPI, DuckDB, pytest, Node 20, Vue 3, Vite 6, GitHub Actions, PowerShell/Git.

**Spec:** `docs/superpowers/specs/2026-10-15-standalone-repository-migration-design.md`

## Global Constraints

- Source root: `F:\VerbalVis2 - 副本 (4)7月15\refactor_next`.
- Destination root: `C:\verbalvis` (Windows resolves the existing empty `C:\VerbalVis` directory to the same location).
- Copy; do not move, delete, reset or clean the source tree.
- Do not copy parent Git history, real Olist CSVs, credentials, Trace, participant data, raw audio, caches, build output or `.superpowers` snapshots.
- Preserve application behavior, the existing Vue presentation and current Python import identity during migration.
- Push only to a newly created private GitHub repository. Do not make the repository public, add a license, or invent citation authorship during migration.
- Begin the paper runtime refactor only after the standalone baseline is green and clean.

## Review Focus

- A relative `VERBALVIS_CONFIG` launched outside the repo must resolve from the repository root.
- Olist configuration must resolve to the ignored `datasets/olist/data` directory and never to the old parent tree.
- The export must exclude nested `node_modules`, `dist`, `.superpowers`, caches and consent-controlled data.
- Editable Python installation and script imports must work from the standalone root on a clean machine.
- The destination must remain usable without Olist CSVs by running the bundled Education configuration.

---

### Task 1: Freeze and inventory the source baseline

**Files:**
- Read: `README.md`, `.gitignore`, `pyproject.toml`, `frontend/package-lock.json`
- Produce outside Git: a timestamped command log and file inventory for the migration session

**Interfaces:**
- Consumes: current source tree and existing test commands
- Produces: a recorded source baseline and explicit source/destination paths

- [ ] **Step 1: Resolve and record both absolute paths**

Set PowerShell variables named `$MigrationSourceRoot` and `$MigrationTargetRoot`; verify the source ends in `refactor_next`, the destination is `C:\verbalvis`, is empty, and the two resolved paths differ.

- [ ] **Step 2: Run the source baseline checks**

Run:

```powershell
python -m pytest tests -q
Push-Location frontend
npm test
npm run build
Pop-Location
python scripts/analyze_traces.py tests/fixtures/trace_v2_analyzer.jsonl --strict
```

Expected: 296 or more Python tests pass, 64 or more frontend tests pass, the build succeeds, and the Trace fixture reports zero diagnostics. Record exact counts rather than hard-coding them as future requirements.

- [ ] **Step 3: Inventory excluded material**

Confirm the source `.gitignore` covers `.env`, Trace, schedules, participant data, raw audio, build output and both conventional Olist data locations. List any existing excluded files without printing their contents.

- [ ] **Step 4: Record the source file manifest**

Record relative path, byte size and SHA-256 for files eligible for export. Exclude the Global Constraints list before hashing.

### Task 2: Export an allowlisted standalone tree

**Files:**
- Copy: `.github/`, `backend/`, `configs/`, `datasets/`, `experiments/`, `scripts/`, `tests/`
- Copy: `frontend/index.html`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/vite.config.js`, `frontend/src/`, `frontend/tests/`
- Copy: root source, dependency and approved Markdown files
- Exclude: every path in the design's Excluded content section

**Interfaces:**
- Consumes: source manifest from Task 1
- Produces: an unversioned standalone destination tree

- [ ] **Step 1: Create the empty destination**

Create only the resolved `$MigrationTargetRoot`; stop if it contains any file.

- [ ] **Step 2: Copy approved directories and files**

Use explicit directory/file lists or `robocopy` exclusions. Do not copy the source directory wholesale and then rely on Git ignore rules to hide sensitive files.

- [ ] **Step 3: Verify exclusion rules against the physical destination**

Assert that `.git`, `.superpowers`, `.env`, `node_modules`, `dist`, caches, `traces`, `pilot_sessions`, `participant_data`, `raw_audio`, real Olist CSVs, `*.lnk` and the parent ZIP are absent.

- [ ] **Step 4: Scan for old-machine references and credentials**

Search source/config/docs for `F:\VerbalVis2`, `C:\Users\admin`, API-key shaped values and private URLs. Allowed examples must contain placeholders only.

### Task 3: Make configuration paths standalone

**Files:**
- Modify: `configs/olist.json`
- Modify: `backend/main.py`
- Modify: `README.md`
- Modify: `PILOT_RUNBOOK.md`
- Test: `tests/test_app.py`
- Test: `tests/test_initial_dashboard.py`

**Interfaces:**
- Consumes: destination repository root derived from `backend/main.py`
- Produces: `read_config(config=None) -> dict` with root-relative config resolution and repository-local Olist configuration

- [ ] **Step 1: Write the failing Olist path test**

Add `test_olist_config_uses_ignored_repo_local_data_directory`: load `configs/olist.json`, assert `dataset.data_dir == "datasets/olist/data"`, assert it contains no `..`, and assert `.gitignore` ignores that directory.

- [ ] **Step 2: Verify the Olist path test fails**

Run the single test. Expected: FAIL because the current value is `../backend/data/olist`.

- [ ] **Step 3: Change the Olist data location**

Set `configs/olist.json` `dataset.data_dir` to `datasets/olist/data`; update README and pilot setup instructions to copy local CSVs there.

- [ ] **Step 4: Verify the Olist path test passes**

Run the single test and the Olist adapter tests.

- [ ] **Step 5: Write the failing config-root test**

Add `test_relative_env_config_resolves_from_repository_root`: change the process working directory to a temporary directory, set `VERBALVIS_CONFIG=configs/education.json`, call `read_config()`, and assert the Education interface is loaded.

- [ ] **Step 6: Verify the config-root test fails**

Expected: FAIL with file-not-found because the current implementation resolves the environment value from the process working directory.

- [ ] **Step 7: Implement root-relative config resolution**

In `read_config`, preserve absolute paths and resolve relative explicit/environment config paths against `ROOT` before reading them.

- [ ] **Step 8: Run path and application tests**

Run `tests/test_app.py`, `tests/test_initial_dashboard.py`, `tests/test_olist_adapter.py`, then the complete Python suite.

- [ ] **Step 9: Remove stale standalone-path text**

Change the missing-build hint in `backend/main.py` from `refactor_next/frontend` to `frontend`. Remove or clearly label historical machine-specific paths in `DASHBOARD_REPORT.md`, and update documents that describe this code as merely a parent-repository subtree.

- [ ] **Step 10: Commit the standalone path contract**

Commit message: `fix: make dataset configuration repository relative`.

### Task 4: Rebuild the destination environment

**Files:**
- Verify: `pyproject.toml`, `requirements.txt`
- Verify: `frontend/package.json`, `frontend/package-lock.json`
- Modify only if verification fails: dependency metadata and CI workflow

**Interfaces:**
- Consumes: standalone source and dependency manifests
- Produces: reproducible local Python and Node installations

- [ ] **Step 1: Create a fresh Python 3.11 virtual environment outside the repository**

Install with `python -m pip install -e <destination>`. Do not reuse packages from the source environment when deciding whether metadata is complete.

- [ ] **Step 2: Run backend and research-tool tests from the destination**

Run `python -m pytest tests -q`, schedule-generation tests, pilot-audit tests and strict Trace fixture analysis.

- [ ] **Step 3: Rebuild frontend dependencies from the lockfile**

Run `npm ci`, `npm test` and `npm run build` in the destination frontend directory.

- [ ] **Step 4: Run the credential-free Education smoke check**

Start the application with the Education config, verify `/api/health`, `/api/dataset` and the built frontend, then stop it. The missing Qwen key may block a live voice session but must not block dataset and static-app inspection.

- [ ] **Step 5: Run the local Olist smoke check when CSVs are available**

Copy/link the nine CSVs into ignored `backend/data/olist/`, run adapter correctness and initial-dashboard smoke tests, and confirm no CSV appears in `git status`.

### Task 5: Establish the standalone Git baseline

**Files:**
- Create: destination `.git/`
- Verify: destination `.gitignore`, release documents and CI

**Interfaces:**
- Consumes: verified destination tree
- Produces: clean `main` baseline and a local pre-refactor tag

- [ ] **Step 1: Initialize a new repository**

Run `git init -b main` in the destination. Do not attach the dirty parent repository as history.

- [ ] **Step 2: Inspect the exact staged set**

Run `git add --dry-run .`, inspect every category, then stage. Confirm excluded and sensitive artifacts remain absent.

- [ ] **Step 3: Complete release hygiene checks**

Run the absolute-path/credential scan, `git check-ignore` checks and all automated suites once from the staged tree.

- [ ] **Step 4: Create the baseline commit and local tag**

Commit message: `chore: establish standalone VerbalVis research baseline`.

Create local tag: `standalone-baseline-2026-10-15`.

- [ ] **Step 5: Verify repository state**

Expected: `git status --short` is empty and the baseline commit contains no ignored data, generated build, credentials or old absolute paths.

### Task 6: Create and push the private GitHub repository

**Files:**
- Verify only: local Git history and remote configuration

**Interfaces:**
- Consumes: clean verified `main` baseline
- Produces: new private GitHub repository with upstream `main`

- [ ] **Step 1: Confirm GitHub identity and repository name**

Use the authenticated GitHub account and choose `verbalvis` if available. If it conflicts, use `verbalvis-rrt` without overwriting or reusing an existing repository.

- [ ] **Step 2: Create a private empty repository**

Do not initialize it with README, license or `.gitignore`; the verified local repository is authoritative.

- [ ] **Step 3: Push and verify**

Add the new remote as `origin`, push `main` and the standalone baseline tag, then verify the remote repository visibility is private and the remote commit matches local `HEAD`.

### Task 7: Prepare the paper runtime refactor handoff

**Files:**
- Create later: `backend/execution.py`
- Modify later: `backend/response_protocol.py`, `backend/realtime.py`, `backend/main.py`
- Modify later: frontend RRT protocol integration and corresponding tests

**Interfaces:**
- Consumes: the approved standalone baseline
- Produces: isolated branch for the already approved paper-first architecture

- [ ] **Step 1: Create the refactor branch only when architecture work resumes**

Run `git switch -c codex/paper-runtime-refactor`. Do not include unfinished architecture changes in the migration baseline.

- [ ] **Step 2: Re-run the baseline suites before the first architecture edit**

Record the exact passing counts in the new repository progress log.

- [ ] **Step 3: Execute the separate paper-runtime plan**

Implement the previously approved commit-linearization and `execution.py` design through failing timing tests first. Migration is complete at this point; this step begins the next project phase.

## Plan self-review

- The plan covers source preservation, physical export, path correctness,
  dependency reconstruction, data/privacy exclusion, Git initialization and the
  handoff to the runtime refactor.
- Migration and architecture changes have independent acceptance gates.
- Every path-changing production edit has a failing test before implementation.
- The package name remains unchanged by explicit design, avoiding a hidden
  import migration.
- The source remains recoverable throughout the process.
