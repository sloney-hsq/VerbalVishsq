import test from "node:test";
import assert from "node:assert/strict";

import { projectLegacyEvents } from "../src/rrtLegacyProjection.js";

test("projects every compatibility event from one RRT frame synchronously in wire order", () => {
  const seen = [];
  projectLegacyEvents(
    {
      event: "dashboard_commit",
      legacy_events: [
        { type: "tool_call", call_id: "call-1" },
        { type: "dashboard_commit", dashboard_revision: 5 },
        { type: "tool_result", call_id: "call-1" },
        { type: "tool_execution_finished", status: "succeeded" },
      ],
    },
    (event) => seen.push(event.type),
  );

  assert.deepEqual(seen, [
    "tool_call",
    "dashboard_commit",
    "tool_result",
    "tool_execution_finished",
  ]);
});
