# Public release checklist

Private collaboration and public release are separate states; see README.md for the repository-visibility policy.

The repository is technically prepared for review but is **not yet authorized for public release**. Complete every unchecked item before creating the public GitHub repository or archival release.

## Maintainer decisions still required

- [ ] Select and add the software license. This is a maintainer/legal decision; the implementation does not assume MIT, Apache-2.0, or another license.
- [ ] Add `CITATION.cff` with the final author names, affiliations/ORCIDs where desired, repository URL, preferred title, and version. Do not publish a fabricated contributor identity.
- [ ] Confirm the distribution terms and citation/source for the Olist data. The current repository does not copy the real Olist CSV directory.
- [ ] Obtain the required institutional ethics approval/waiver and freeze consent, retention, exclusion, retry, task-time-limit, questionnaire, semantic coding, and analysis plans before recruitment.

## Repository hygiene

- [ ] Publish only this repository root; do not include unrelated source history or workspace material.
- [ ] Confirm `git status` contains only intended source, tests, docs, and small synthetic fixtures.
- [ ] Confirm no `.env`, API key, `traces/`, `pilot_sessions/`, raw audio, participant data, local shortcut, IDE state, `node_modules/`, `dist/`, cache, or real Olist CSV is tracked.
- [ ] Search the final tree for local absolute paths, credentials, participant identifiers, and private URLs.
- [ ] Replace draft dates/version numbers and add the final repository URL to the README and citation metadata.

## Reproducibility gate

- [ ] In a clean Python 3.11.14 environment, `python -m pip install --require-hashes -r requirements.lock` followed by `python -m pip install --no-deps -e .` succeeds.
- [ ] `python -m pytest tests -q` passes; skipped real-data checks are reported explicitly.
- [ ] From the repository root, run `cd frontend`, then `npm ci`, `npm test`, and `npm run build`, followed by `cd ..`; these commands succeed under Node 20.
- [ ] GitHub Actions passes from a clean checkout without credentials or the real Olist dataset.
- [ ] `python scripts/prepare_pilot.py ...` generates the expected two-trial schedule for all four sequence IDs.
- [ ] `python scripts/analyze_traces.py <fixture> --strict` succeeds and does not echo consent-controlled content.
- [ ] `python scripts/audit_pilot.py --schedules <dir> --traces <dir> --strict` reconciles every planned formal trial, reports zero diagnostics, and keeps practice sessions separate.
- [ ] Freeze `REVISION_CODEBOOK.md`, coder training examples, blinding procedure, and adjudication rules before semantic coding begins.

## Claim and artifact gate

- [ ] README claims match the released code and distinguish deterministic verification, real-provider validation, pilot observations, and formal user-study evidence.
- [ ] Screenshots contain no participant data and correspond to the released commit.
- [ ] Paper/proposal terminology matches the canonical runtime conditions: `turn_taking` and `revision_enabled`.
- [ ] A release tag identifies the exact code used for each pilot/formal-study wave; post-freeze fixes document affected trials.
