# Standalone release and migration documentation audit

Audit date: 2026-10-15  
Scope: release/migration-facing text and metadata in the standalone checkout. This is an edit plan, not a release authorization. Line numbers refer to the inspected tree.

## Priority 0 — fix before any commit or remote push

| File:line | Finding | Recommended replacement or edit |
|---|---|---|
| `backend/main.py:290` | The user-facing missing-build error still tells users to build from the former nested frontend directory. | Replace the message with: `Run npm ci && npm run build in frontend, then restart; or use Vite on port 5174.` |
| `README.md:44` | It says Olist defaults to the old parent-relative data location. `configs/olist.json:3` already correctly uses `datasets/olist/data`. | Replace the paragraph with: `该配置默认读取仓库内且被 Git 忽略的 \`datasets/olist/data\`；不会复制数据。将九个 Olist CSV 放入该目录，或在本地（已忽略）配置中指定其他路径。配置中的相对接口、数据和 Trace 路径均相对仓库根目录。` |
| `OLIST_ADAPTER_REPORT.md:50` | The published smoke-test record names the obsolete parent-relative Olist source. | Replace with: `Configured source during this historical smoke test: repository-local ignored Olist data directory. Snapshot version during the final run: \`olist-5-8e2b55985d02985e\`.` Do not retain a workstation-relative path. |
| `docs/superpowers/plans/2026-10-15-standalone-repository-migration.md:118,181` | Two unchecked migration steps state the obsolete Olist directory as the current or target location. | At 118 replace the expected old value with `an obsolete parent-relative Olist data path`; at 181 replace the destination with \`datasets/olist/data/\`. |
| `docs/superpowers/plans/2026-10-15-standalone-repository-migration.md:146` | The plan explicitly records the still-unfixed error text in `backend/main.py`. | Once the P0 code edit is made, replace this step with a completed historical note: `Verified that the missing-build hint names \`frontend\`; removed machine-specific and parent-repository wording from release-facing documents.` |
| `backend/main.py:121` and `README.md:40-46` | The README implies repository-root-relative configuration, but `read_config()` constructs a relative explicit/environment path from the process working directory. This makes the launch contract dependent on where Uvicorn was started. | Change `read_config()` so non-absolute explicit/environment config paths are resolved against `ROOT`; then state once in README: `Run backend commands from the repository root. Relative VERBALVIS_CONFIG values are resolved from that root.` |

## Priority 1 — remove local-machine and parent-checkout history from release-facing files

The following matches are local-history references. If the migration plan/spec must be retained, first add an `Archived migration record; not current setup instructions` banner, then apply the redactions below. A public repository should not expose source-checkout, user-profile, or drive details merely because the record is historical.

| File:line | Finding | Recommended replacement or edit |
|---|---|---|
| `DASHBOARD_REPORT.md:26` | Contains both a user-profile Python executable and the former F-drive checkout name/date. | Replace the whole line with: `Validation used Python 3.11 from a local virtual environment; commands were run from the standalone repository root.` |
| `docs/superpowers/specs/2026-10-15-standalone-repository-migration-design.md:5-9` | Names the former F-drive source checkout and the local destination. | Replace with: `This archived record describes copying the approved implementation from a separate source checkout into this standalone repository. The source checkout remained unchanged until acceptance checks passed.` |
| `docs/superpowers/plans/2026-10-15-standalone-repository-migration.md:15-16` | Names both source and destination absolute paths. | Replace with: `- Source and destination paths were recorded in a private migration log; they are intentionally omitted from this repository.` |
| `docs/superpowers/plans/2026-10-15-standalone-repository-migration.md:45` | Prescribes an old nested-directory suffix and local destination path. | Replace with: `Verify that source and destination are distinct resolved paths; keep their values in the private migration log.` |
| `docs/superpowers/plans/2026-10-15-standalone-repository-migration.md:96` | Prints the former drive path and user-profile path as search literals. | Replace with: `Search source, configuration, and documentation for machine-specific absolute paths, credentials, and private URLs. Allowed examples must use placeholders only.` |
| `docs/superpowers/plans/2026-10-15-standalone-repository-migration.md:7,18,195` | Describes the application as a subtree of a dirty parent repository, although this checkout is now the repository root. | Replace `subtree`/`parent repository` wording with `approved source snapshot`/`unrelated source history`; e.g. line 195: `Initialize a new repository in the destination without importing unrelated source history.` |
| `docs/superpowers/specs/2026-10-15-standalone-repository-migration-design.md:13-16,40,47,104-105,107` | Repeatedly frames the project as an untracked child of a parent repository. | Use `source checkout` rather than `parent repository`, and `application snapshot` rather than `untracked subtree`; e.g. lines 13-16: `The migration copies the approved application snapshot, tests, research utilities and documentation. It intentionally does not import unrelated source history.` |
| `DESIGN_ZH.md:15` | Calls the implementation an independent `refactor_next` implementation in a parent repository. | Replace with: `审计对象是本仓库中的独立实现，不是旧实验版。` |
| `PROGRESS.md:52`, `TASKS.md:11,89` | Historical progress claims say no tag/push occurred because of a dirty parent repository. They read as current release status and conflict with the private-migration intent. | Move these entries under a clearly marked `迁移前历史记录` heading, or replace with: `迁移前检查未在源工作区创建 tag 或推送；独立仓库的 tag 和远程状态以当前 Git 记录为准。` |
| `STUDY_FREEZE_CHECKLIST.md:17` | `父目录` is ambiguous and retains the previous checkout model. | Replace with: `从干净的仓库根目录发布，不要从包含多个项目改动的目录运行。` |

## Priority 1 — establish one private-versus-public policy

| File:line | Finding | Recommended replacement or edit |
|---|---|---|
| `README.md:3` | States that the project has not been published to GitHub, while the migration design/plan describe a private GitHub baseline. These are incompatible as enduring setup statements. | Replace the final bold sentence with: `**本仓库仅限私有协作；尚未获准公开发布。任何公开 GitHub 仓库、公开 issue、release、tag 或归档均须先完成 [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) 的全部门槛。**` |
| `docs/superpowers/specs/2026-10-15-standalone-repository-migration-design.md:69-73,106-107` and `docs/superpowers/plans/2026-10-15-standalone-repository-migration.md:20,215-234` | These correctly require a private baseline but do not point readers to the canonical ongoing release policy. | Keep the private-baseline requirement, add: `The repository visibility and public-release policy are defined in README.md and RELEASE_CHECKLIST.md.` |
| `RELEASE_CHECKLIST.md:1-3` | Correctly blocks public release, but it is not linked as the canonical policy from the README/migration docs. | Keep the gate text and add one line: `Private collaboration and public release are separate states; see README.md for the repository-visibility policy.` |
| `SECURITY.md:3,13` | The public-issue fallback is acceptable only for non-sensitive coordination, but it can be misread as permission to disclose private research material. | Append: `This fallback does not authorize publishing participant data, traces, credentials, or details that would make the repository public.` |

## Priority 2 — make versions and working directories reproducible

| File:line | Finding | Recommended replacement or edit |
|---|---|---|
| `README.md:20-31` | Python/Node versions are named, but the supported Python target is not pinned and the initial command sequence relies on an implicit root working directory. | Start the section with: `From the repository root, use Python 3.11 and Node.js 20.19.0 (or a compatible Node 20 release).` Add a virtual-environment activation step before `pip install`; label `cd frontend` as the only frontend-directory command and explicitly say `cd ..` returns to the repository root. |
| `README.md:40-46,218-230` and `PILOT_RUNBOOK.md:28-47` | Multiple commands say `本目录` but never define it as the repository root; frontend commands require a different directory. | Add a shared convention near each command section: `Unless a command begins with cd frontend, run it from the repository root.` Update pilot line 40 to name \`datasets/olist/data/\`, not merely the JSON field. |
| `pyproject.toml:9` and `.github/workflows/ci.yml:19-22` | Metadata permits Python 3.11+, while CI verifies only 3.11; no local version selector makes the tested baseline obvious. | Retain `requires-python = ">=3.11"` if newer Python is intentionally supported. Add root `.python-version` containing exactly `3.11` to make the release/test baseline reproducible. If 3.11 is the only supported line, instead set `requires-python = ">=3.11,<3.12"` and document that choice. |
| `frontend/package.json:1-22` and `.github/workflows/ci.yml:35-39` | CI uses Node 20 and README calls for 20.19+, but the package manifest contains no engine bound or local selector. | Add `"engines": { "node": ">=20.19 <21" }` at the package top level, and add root `.nvmrc` containing exactly `20.19.0`. Keep CI's `node-version: "20"` only if any current Node 20.x is accepted; otherwise make it `20.19.0`. |

## Ignore and repository-attribute audit

| File:line | Finding | Recommended replacement or edit |
|---|---|---|
| `.gitignore:4-6,22-23` | Correct: it ignores `.venv/`, `node_modules/`, `dist/`, the legacy Olist location, and the required repository-local `datasets/olist/data/`. | Retain these rules. The old `backend/data/olist/` rule may remain temporarily for defensive cleanup, but add a comment marking it as a legacy local-data safeguard so it is not documented as the current location. |
| `.gitignore:7,19-21` | Correctly ignores traces, pilot sessions, participant data, and raw audio. | Retain these rules. |
| `.gitignore` (end) | It does not explicitly cover experiment-generated data/results beneath `experiments/`; only the checked-in manifest currently exists. | Add narrowly scoped rules: `experiments/**/data/`, `experiments/**/results/`, and `experiments/**/outputs/`. Do not ignore `experiments/*.json`, because the tracked pilot manifest is source material. |
| repository root | No `.gitattributes` exists. Cross-platform line endings and binary data classification are therefore unspecified. | Add the minimal file: `* text=auto eol=lf` followed by `*.csv binary`, `*.jsonl binary`, `*.wav binary`, and `*.zip binary`. If CSV review diffs are desired, omit only the `*.csv binary` line. |

## Verified current facts and scope notes

- `configs/olist.json:3` is already the correct standalone path: `datasets/olist/data`.
- `.gitignore` already covers the required local Olist directory, virtual environment, frontend dependencies, build output, traces, and several participant-data locations.
- No `.gitattributes`, `.python-version`, or `.nvmrc` exists at the repository root.
- `frontend/package.json` has no `engines` field; CI selects Python 3.11 and Node 20.
- The checkout currently has only untracked files, so documentation must not claim a clean baseline commit, tag, remote, or private GitHub push until those states are actually established and verified.

