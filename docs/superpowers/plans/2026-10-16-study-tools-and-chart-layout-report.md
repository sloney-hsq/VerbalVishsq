# Study tools and chart layout acceptance

Date: 2026-10-16. Worktree: `codex/visual-analysis-tools`.

Status: implementation and offline/browser acceptance complete. Real provider-backed voice-study preflight remains external and is not claimed complete.

## Scope

Enhance aggregate, compare_segments, distribution and relationship; add compare_periods; provide six Olist exploration tasks and deterministic tool replay. Improve chart layout without changing the voice protocol or introducing an intent encoder. This is a bounded exploratory-analysis toolkit, not an arbitrary statistics platform.

The two existing GPT-5.6-Sol agents implemented backend and frontend separately. The parent reviewed their changes and performed browser and integration checks. Work remains isolated; no merge or push.

## Frontend evidence

- Commits: `feb956b`, `77e593a`, `5d6e2d9`.
- Parent fresh verification: `npm test` — 86 passed; `npm run build` — exit 0. Existing Vega bundle-size warning remains.
- Real Vue component harness rendered all nine legacy Olist outputs. Browser QA found and corrected runtime-template compilation, reactive metadata cloning, and paged heatmap denominator projection bugs.
- Real data has 73 heatmap categories in this scope. Four pages show 20/20/20/13 categories; last-page Next is disabled. All-mode returns to the previous page. Full-data color domains remain fixed; full view scrolls internally.
- 360px and 768px DOM measurements showed no root horizontal overflow. 1440px view retained the conversation-sidebar-sized space and two-column chart grid. Synthetic three-facet checks rendered two columns on desktop and one on narrow screens; a 55-category horizontal bar retained readable rows with internal scrolling.
- Period tooltips include actual bucket dates, presence and record count. Expandable notices expose suppressed comparisons and date-coverage limitations. Quantile tooltips include valid and missing counts.

## Runnable previews

- `http://127.0.0.1:8017/index.html`: six-family static real-data preview with heatmap page controls.
- `http://127.0.0.1:5175/visual-check.html`: production ChartSlot harness using nine legacy outputs, with optional synthetic layout edge cases.
- `http://127.0.0.1:5176/visual-check.html`: production ChartSlot harness using the new study-tool replay output.

These are loopback-only development servers. Restart instructions are in README. Generated fixtures live in the ignored `.superpowers/sdd/2026-10-16-study-tools-and-chart-layout/` workspace; raw CSVs are unchanged.

## Backend and combined acceptance

- Backend commit: `f070eaf` (`feat: add Olist study analysis tools`). Parent fresh full suite: `.venv/Scripts/python.exe -m pytest -q` — **370 passed**, one existing Starlette/httpx deprecation warning, 26.78 seconds.
- Parent fresh study replay: `scripts/check_study_tools.py` — all six task chains succeeded, **16 revisions**. Export: `.superpowers/sdd/2026-10-16-study-tools-and-chart-layout/study-tools-parent-views.json`.
- Parent fresh legacy replay: `scripts/check_visual_analysis.py` — **15 successful steps/revisions**; selection, baseline fork, shared scope and undo remained compatible. Export: `legacy-parent-views.json` in the same directory.
- Regenerated six legacy chart-family SVGs and compiled/rendered all six new study outputs. Refreshed the real Vue study harness: all six view headings and charts present, no render error or root horizontal overflow.
- Review found and corrected pooled segment/period quantile populations, snapshot threshold materialization, shared-date clipping, eligible-versus-valid denominators, mixed fixed/dynamic controls, segment breakdown pairing, complete-domain TopK and period groups, reserved measure-ID collisions, and dynamic aggregate values incorrectly eligible for raw-row selection.
- Dedicated regression fixtures now include more than 100 groups, hidden fixed-metric `having`, row-aligned valid/eligible counts after control operations, mixed aggregates with local quantile rules, and aggregated-value highlight versus filter semantics. Oversized internal complete-group queries fail explicitly rather than silently dropping groups.

## Six exploration directions

Participant-facing open prompts are in `experiments/olist_study_task_pool.json`. Researcher-only deterministic call chains are in `scripts/check_study_tools.py`.

1. Regional delivery risk: retain adequate volume, revise time scope and extreme-value exclusions.
2. Delivery period change: compare explicit periods while checking date coverage and composition.
3. Review–delivery association: compare reference groups and revise thresholds or regions.
4. Freight-definition robustness: compare mean/quantile/registered-ratio interpretations.
5. Freight–attribute association: inspect weight, volume and price relationships and their limits.
6. Seller delivery stability: compare bounded seller scopes and sensitivity to volume/extremes.

## Performance and capability limits

On this machine's final real-data replay, the full relationship call evaluated 99,627 eligible/valid item pairs in 652 ms; the shared-scope update took 780 ms. The seller task explicitly revised a ten-seller scope to five, reducing eligible observations from 13,678 to 7,952. These are single-run offline timings, not latency guarantees or speech/model response times.

Exact quantiles, dynamic measures and correlation calculations still materialize observations in backend Python; very large datasets and many period buckets require further profiling. Display sampling does not approximate the reported correlations. Tool coverage is bounded to the approved task pool, registered fields/statistics and explicit order/item semantics, not universal analysis completeness. Generalization is through dataset adapters and declared metadata; it does not automatically infer semantics for arbitrary CSVs.

## Research boundary

The six-task pool is not a balanced formal-study allocation. Pilot difficulty, time limits, task assignment and exclusion rules still need freezing. Offline replay is deterministic code execution, not evidence of model tool-selection quality or user benefit.

The visual harness does not connect a provider, open a microphone or simulate voice participants. Real provider/device/Trace preflight and both dialogue conditions remain required before a voice user study. Comparing two voice conditions alone does not establish that voice causes more fine-grained revisions than text.

## Follow-up: presentation and English product language

The owner's browser feedback required removing internal view IDs and the development sidebar, fitting cards to rendered content, and compactly arranging unequal card heights. Shared chart cards now use natural heights and a resize-observed grid. Long horizontal bars offer 14-category pages and a complete scrolling view with a fixed full-data numerical domain. Heatmap paging and source-aligned validity metadata remain intact. Chart labels use the current measure definition, so an ID originally named P90 correctly displays P80 after its definition changes.

All product-facing copy and participant task prompts use English. The runtime instructions require English spoken and written responses, chart titles, and explanations while preserving verbatim user transcripts and raw data values. Both task material manifests are version 1.1; historical schedules are not rewritten. Repository-wide requirements are in `AGENTS.md`.

Follow-up verification: frontend 89 tests passed and production build succeeded; 27 relevant Python prompt, pilot-schedule and study-flow tests passed. Live browser checks found no Chinese interface text, no internal-ID header or sidebar, and no render error. At a 390px viewport, every rendered SVG matched its chart body width and the page had no horizontal overflow. Category paging reached 15–27 of all 27 states. Actual English voice delivery still requires a new provider-backed session and was not exercised by these checks.

## Follow-up: Chinese author reference and 16:9 desktop design

The Chinese author handbook at `docs/author/study-tasks.zh-CN.md` preserves the six study prompts and both original pilot prompts, with exploration steps, tools, rehearsal phrases, and interpretation notes. English participant materials remain version 1.1. `AGENTS.md` now requires Chinese explanations for the owner, synchronization of author references with participant materials, professional visualization aesthetics, and a 1920x1080 primary / 1366x768 compatible desktop target.

The shared grid now supports three columns in a wide workspace, two at medium width, and one when narrow. The demonstration uses viewport height with scrolling inside the chart area. Plot/legend typography is 12px; legends wrap according to available card width. Cards retain content-based heights and complete categorical pages.

Fresh verification: frontend 90 tests passed and production build succeeded. At 1920x1080, all six study charts fit in three columns and two levels, with no horizontal overflow. At 1366x768, two columns use local vertical scrolling (720px visible chart area / 1289px content), all SVG widths match their containers, no cards overlap, and the document stays 768px high. Browser text remains English and temporary viewport overrides were reset. These observations describe the six-view demonstration; the provider-backed Dashboard conversation remains a separate acceptance boundary.
