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

## Visual presentation

- Size cards to their content and verify the actual rendered chart width after responsive layout changes.
- Keep all categories reachable when introducing presentation paging; preserve analytical data, global scales, selection semantics, and dashboard revisions.
- Verify visible changes in the running application, including a narrow viewport, rather than relying on compilation alone.

## Workspace

Continue this feature in the attached isolated worktree. Preserve unrelated changes. Do not merge or push without the user's instruction.
