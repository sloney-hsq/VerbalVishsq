## Task 4: Responsive chart layout and heatmap browsing

**Files:** Modify `frontend/src/chartLayout.js`, `chartSpecs.js`, `specFactory.js`, `components/ChartSlot.vue`, `components/Dashboard.vue`, relevant unit/filter presentation helpers; extend frontend tests; modify `frontend/scripts/renderVisualCheck.mjs` and optionally add a separate study-render script.

**Interfaces:** Preserve current createSpec call sites by adding optional third `presentation` argument. `chartLayoutForView(view, availableWidth)` returns card span/height, plot dimensions, ordered full domains and paging policy. `heatmapPresentation(view, {pageIndex,mode}, availableWidth)` returns visible category projection and full-data scale domain, without mutating view. Presentation is local component state only.

- [ ] Write failing layout tests for 72 Y categories ×2 X values: four pages of 20 categories, last12; every category's two cells stay together. Test 24-category threshold, no paging for binned_2d, fixed full-data color domains, source order, empty data, long labels and off-page selections.
- [ ] Run `npm test` for RED. Implement pure layout/presentation helpers, with complete rows prepared before projection; preserve full-data denominator/selection metadata aligned with rows.
- [ ] Replace fixed card heights with spec layout tiers, actual-container-width two/one-column layout at 880px, stable creation order, full-width dense heatmap/multiseries/facet cards, two-line title and wrapping metadata. Keep existing conversation/microphone workflow unchanged.
- [ ] Add accessible Previous/Next/Page/View all controls, 20-category pages, top horizontal continuous legend, ~22px rows, max220px labels, internal full-view scrolling; keep complete data and revision/digest untouched. New source revision with same category domain preserves page; changed domain clamps page.
- [ ] Repair facet wrap with explicit child dimensions and supported autosize. Format percentage_points and correlation distinctly from ratios; new result kinds use column metadata, no Olist branches. Render structured OR filter labels without object-string artifacts.
- [ ] Update static demo to share layout/spec logic, output page/full SVGs and working native buttons, full-row heatmap and bounded full-view scroll. Keep compatibility output names and distinguish full versus paged content.
- [ ] Run frontend suite and build; render actual Olist SVGs, inspect 360/768/1440px layouts and actual Vue cards when browser capability permits. Verify rapid re-render/unmount lifecycle and no horizontal page overflow. Report any unavailable browser acceptance, do not substitute compilation claims.
- [ ] Commit only frontend files after coordination; write frontend report with tests, artifact paths and unresolved visual concerns.

