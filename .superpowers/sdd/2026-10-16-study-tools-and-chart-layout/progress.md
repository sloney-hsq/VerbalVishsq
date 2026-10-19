# SDD ledger — plan: docs/superpowers/plans/2026-10-16-study-tools-and-chart-layout.md

Base: 98db3e9. Worktree: C:/Users/admin/.codex/worktrees/visual-analysis-tools/VerbalVis.

## Execution decisions

- User explicitly confirmed the written design and said to hand to subagents and start. Preserve the chosen two GPT-5.6-Sol agents; no further scope approval gate or extra implementation agents.
- Backend /root/study_tools_56 owns Tasks 1–3; frontend /root/study_frontend_56 owns Task 4. Parent owns docs and Task 5. File ownership is disjoint; commits are serialized by parent approval. Parent reviews product changes and returns fixes to owner.
- Existing isolated worktree reused per using-git-worktrees. Fresh baseline: Python341 pass / existing httpx deprecation; Node74 pass / existing facet autosize warning. Raw data and node_modules junctions remain read-only.

## Preflight consistency

| Tasks | Shared interface or file | Check |
| --- | --- | --- |
| 1 | Predicates, IDs, patch validation | Backend owns all; schema and runtime changes together |
| 2 | Comparison/distribution/correlation output | Stable wide IDs, new result kinds do not change old rows |
| 3 | Periods and replay | Uses same measures and predicates, no separate statistical definitions |
| 4 | Layout/spec/card/demo | Pure presentation, no store data mutation |
| 5 | Reports and integration | Parent does not edit worker product files |
| 1/2 | Predicate/measure helpers | Backend sequences implementations |
| 1/3 | Filters and measures | Period scope and quantile pooled population from spec |
| 1/4 | Dynamic IDs, OR fields | Frontend uses declared columns and recursively formats filters |
| 2/3 | Comparison formulas | Reuse implementation, no differing percentage-point formulas |
| 2/4 | quantiles/relationship_summary metadata | Declare quantitative fields and distinct units |
| 3/4 | periods and exported replay views | bucket_index/date tooltip and metadata shared contract |
| 1–4/5 | Full tests and visual QA | Verify final combined tree, not only worker reports |

## Progress

- Setup complete. Plan written and baseline verified; task briefs to be dispatched.
- Dispatched Tasks 1–3 to /root/study_tools_56 and Task 4 to /root/study_frontend_56 on 49ac5eb, reusing their requested GPT-5.6-Sol identities.
- Browser control restored: bound existing 8016 demo tab via cua_repl, DOM available. Parent handles browser acceptance, avoiding duplicate UI sessions.
- Verification harness approved: frontend/visual-check.html may mount production chart components from real exported views under Vite dev only. No provider calls, mock voice, new production entry or dependencies. If Dashboard auto-connects, use production ChartSlot plus shared layout and report that boundary.
- Parent browser QA: static 8017 heatmap corrected to wide SVG rendering; Next updates 1–20 to 21–40 of 73 actual categories. Vue 5175 harness initially blank due runtime template compilation; worker fixed with precompiled SFC. Live Vue uncovered Proxy structuredClone failure in normalized composition and missing heatmap valid-count tooltip; returned to frontend owner. 360px/768px DOM measurements show no root horizontal overflow.
- Parent backend review returned in-progress gaps to owner: finite thresholds/pairs, explicit nested-OR rejection and typed between validation, row-aligned denominators, grouped period spine, clipping/extent delta suppression, and distinct bucket-presence counting. Awaiting completed implementation and fresh verification before acceptance.
- Frontend commits feb956b and 77e593a accepted after live QA: nine charts render, no NaN count labels, pager last page 61–73 disables Next, all-mode returns to prior page, 360/768 no root overflow; 1440 facet 2+1 and 360 single-column; 55-category horizontal bar internally scrolls. Parent independently ran 80-test suite/build before edge additions; worker final edge suite84.
- Parent real six-task replay succeeded at 16 revisions and exported study-tools-parent-views.json; served through real Vue components at5176. Period date/count tooltips and expandable out-of-extent notices subsequently verified. This validates the exercised calls, not all statistical contracts.
- Backend completion request at358 tests was NOT accepted: pooled quantile scopes, shared date-clipping suppression, period row metadata, true eligible counts, pre-limit TopK and mixed/fixed segment comparison require further explicit tests and corrections. Commit slot withheld pending correction.
- Final correction review accepted: reserved IDs, mixed local quantiles, 150-group TopK/period domain, raw-filter rejection of aggregated values, hidden fixed having, and row-aligned valid/eligible counts have focused regressions. Backend committed f070eaf and released slot.
- Parent final verification: Python370 passed/one existing warning; frontend86 passed/build success; real study replay16 revisions and legacy replay15 revisions; regenerated six-family SVGs and rendered all six study outputs. Live Vue final study fixture has six charts and no root overflow/render error. Temporary viewport override reset; study and layout tabs retained as deliverables.
- Tasks 1–5 accepted for the bounded offline/browser scope. Keep branch/worktree and loopback previews; no merge/push. External voice/provider/Trace preflight remains unperformed and is explicitly documented.
