## Task 3: Period comparisons and six-task real-data replay

**Files:** Create `datasets/olist/periods.py`, `tests/test_study_periods.py`, `scripts/check_study_tools.py`, `tests/test_study_flows.py`, `experiments/olist_study_task_pool.json`; modify `datasets/olist/interface.py` and relevant result/chart validation.

**Interfaces:** Register `compare_periods` exactly as spec. Summary returns wide rows by period and groups; series additionally emits bucket_index/start/end/present. New result_kind=`periods`; comparison formulas reuse Task 2. Export replay views as a JSON mapping accepted by frontend render scripts.

- [ ] Write failing summary/series fixtures for day, Monday week, month, explicit unequal summary windows, aligned equal-count series, absent buckets, date-range clipping, zero baseline and P90 measures. Assert absent bucket measures are null, not zero; record_count remains 0; no metadata calls presence proof of complete collection.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_study_periods.py -q` and capture RED; implement one period spine plus shared query path, [start,end) boundaries, nonoverlapping windows, reference pairing and coverage warnings.
- [ ] Create the six-task pool using the exact approved IDs/prompts. Do not change the existing pilot manifest or allocation scripts. Keep tasks open-ended; replay call sequences are researcher-only.
- [ ] Implement `run_workflows(data_dir, *, export=None)` in `scripts/check_study_tools.py`; CLI accepts `--data-dir` and `--export`. Exercise all six tasks through real Toolbox drafts, with stable-ID updates, OR, quantile exclusion, baseline fork, period comparison and undo. No model/provider calls.
- [ ] Test synthetic expected values/state invariants; run real Olist replay and export representative views under this plan's ignored artifact directory. Record operation timings and eligible/valid counts, not fabricated study outcomes.
- [ ] Run full Python suite and legacy smoke, then commit owned paths and write backend report. Any inability to complete a required feature must be raised explicitly.

