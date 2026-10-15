import test from "node:test";
import assert from "node:assert/strict";
import { createSSRApp, h } from "vue";
import { renderToString } from "@vue/server-renderer";

import { TranscriptFeedback } from "../src/components/TranscriptFeedback.js";

test("revision feedback renders as small neutral inline labels in SSR", async () => {
  const app = createSSRApp({
    render: () => h("div", [
      h(TranscriptFeedback, { label: "Revision accepted" }),
      h(TranscriptFeedback, { label: "Superseded" }),
    ]),
  });
  const html = await renderToString(app);
  assert.match(html, /Revision accepted/);
  assert.match(html, /Superseded/);
  assert.match(html, /transcript-feedback/);
  assert.doesNotMatch(html, /alert|dialog|error/);
});
