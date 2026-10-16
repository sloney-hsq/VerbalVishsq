# VerbalVis agent principles

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

- Design primarily for a landscape 16:9 computer display at 1920x1080; verify compatibility at 1366x768. Account for browser chrome and any conversation panel rather than assuming the full display is available to plots.
- Use available width deliberately: normally three chart columns on a wide desktop workspace, two at medium width, and one when narrow. Dense matrices and facets may span columns when their content needs it.
- Use the available viewport height for the workspace, with deliberate scrolling inside the analytical area. Do not force every dataset or chart into one screen by shrinking labels or clipping evidence.
- A 16:9 screen does not require every chart or card to have a 16:9 aspect ratio. Size each chart to its data, labels, legend, and analytical purpose.
- Verify both target desktop sizes in the actual browser and restore temporary viewport overrides after checking them. Mobile support is a fallback, not the primary design reference.

## Visual presentation

- Size cards to their content and verify the actual rendered chart width after responsive layout changes.
- Keep all categories reachable when introducing presentation paging; preserve analytical data, global scales, selection semantics, and dashboard revisions.
- Verify visible changes in the running application, including a narrow viewport, rather than relying on compilation alone.

## Workspace

Continue this feature in the attached isolated worktree. Preserve unrelated changes. Do not merge or push without the user's instruction.
