# VerbalVis agent principles

## Current study scope

The current approved scope is a between-subjects study with 12 participants, one formal task and one voice condition per participant: 6 revision_enabled and 6 turn_taking. Each condition assigns 3 participants to each of the two task-pool 2.0 tasks. Do not implement a voice/text comparison, crossover allocation, or a second formal task per participant. The updated design and engineering plan are pending implementation; see [study design](docs/superpowers/specs/2026-10-19-voice-policy-between-study-design.md) and [implementation plan](docs/superpowers/plans/2026-10-19-voice-policy-between-study.md). Preserve the historical pilot and Trace v2.

## Product language: English

The application is demonstrated and evaluated by an international visualization research audience. English is the required product language.

- Write all user-facing interface copy in English: navigation, controls, titles, axes, legends, tooltips, notices, errors, empty states, accessibility labels, and browser document titles.
- Use English for the analytics assistant's spoken and written responses, clarification questions, chart titles, and tool-generated explanatory text, even when a request arrives in another language.
- Write participant-facing study tasks and demonstration materials in English. Version study manifests when changing participant-facing wording; preserve existing session records and schedules.
- Set application documents to `lang="en"`. Keep number and date presentation consistent with the English interface.
- Preserve verbatim user transcripts, raw dataset values, identifiers, API field names, and historical records. Do not fabricate translations of user speech or rename analytical fields to change their display language. Multilingual input recognition may remain supported.
- Keep internal identifiers out of chart headers. Use readable English titles and declared metadata for chart labels; display the actual statistic, units, and reference context.
- New code and future agent changes must maintain this English-language policy. Chinese developer documentation and conversations with the project owner may remain Chinese unless requested otherwise.

## Author language: Chinese

- Explain implementation choices, task meanings, and rehearsal instructions to the project owner in Chinese.
- Maintain a Chinese author reference for every participant-facing task and pilot prompt. When English materials change, update the matching Chinese explanation in the same change.
- The author reference is `docs/author/study-tasks.zh-CN.md`. It is separate from the English runtime and participant materials; never replace it with English-only documentation.

## Visualization aesthetics and analytical integrity

- Treat the application as a professional visual analytics workspace for visualization researchers. Prioritize readable evidence, comparison, and a clear visual hierarchy over decoration.
- Use position and length for quantitative comparisons, restrained categorical colors for identities, sequential color for magnitude, and zero-centered diverging color for signed differences. Do not introduce decorative gradients, 3D marks, or color changes unrelated to data semantics.
- Establish a consistent typography, spacing, alignment, border, and legend system. Use readable plot labels (normally at least 12px on the desktop baseline), short meaningful English titles, and units/statistical definitions taken from declared metadata.
- Preserve explicit or registered category order. Do not silently sort, truncate categories, change scales, or change statistical definitions for appearance. Use clear presentation controls when the user needs another ordering or a subset of categories.
- Keep comparison scales consistent, explain independent scales, and preserve missing-value gaps. Expose sample sizes, sampling, fixed baselines, coverage limitations, and suppressed comparisons without overwhelming the primary chart.
- Use meaningful precision on axes and more detail in tooltips. Avoid raw field names and long internal identifiers as presentation text; keep exact source identifiers available where analytically needed.
- Inspect real data and the complete workspace composition. Check long labels, legends, sparse data, dense heatmaps, paging, and resize behavior; compilation alone does not establish visual quality.

## Desktop target: 16:9

- Design primarily for a landscape 4K 16:9 computer display at 3840x2160. Also verify 2560x1440 and 1920x1080 effective CSS viewports for common display scaling, plus compatibility at 1366x768. Account for browser chrome and the conversation panel rather than assuming the full display is available to plots.
- Use available width deliberately: on the current nine-view wide desktop, place eight equal-width, equal-height cards in a left 2-row by 4-column grid, with one category heatmap in the right column spanning both rows. A quantitative binned heatmap is one of the eight left cards, not a second right-lane matrix. Use two columns at medium width and one when narrow; retain natural-height fallback for additional views or facets. Fit the current nine-view 4K dashboard without canvas or plot scrollbars; preserve complete data through explicit category paging when needed, not clipped marks.
- Place Conversation below the full-width analytical canvas at 25% of the viewport height, including when empty. Allow the dock to collapse outside formal trials and preserve complete transcripts and study controls with independent scrolling.
- Put a visible ordinal to the left of every chart title: left comparison cards first (1–8 on the current dashboard), then the right category matrix (9). Keep numbers independent of viewport size, and project the identical display_number-to-ID mapping to model context and dashboard inspection. Do not use raw array positions to resolve spoken view numbers or rewrite authoritative chart IDs.
- Use the available viewport height for the workspace, with deliberate scrolling inside the analytical area. Do not force every dataset or chart into one screen by shrinking labels or clipping evidence.
- A 16:9 screen does not require every chart or card to have a 16:9 aspect ratio. Size each chart to its data, labels, legend, and analytical purpose.
- Verify both target desktop sizes in the actual browser and restore temporary viewport overrides after checking them. Mobile support is a fallback, not the primary design reference.

## Visual presentation

- Keep the interface simple, following the older frontend's single toolbar, regular cards and bottom row-based transcript. Do not add decorative preview-state panels or repeated placeholder instructions. Keep one honest offline indicator for saved-result previews. Use equal comparison cards on the nine-view desktop and content sizing for fallback layouts; verify the actual rendered chart dimensions.
- Keep all categories reachable when introducing presentation paging; preserve analytical data, global scales, selection semantics, and dashboard revisions.
- Verify visible changes in the running application, including a narrow viewport, rather than relying on compilation alone.

## Workspace

Continue this feature in the attached isolated worktree. Preserve unrelated changes. Do not merge or push without the user's instruction.
