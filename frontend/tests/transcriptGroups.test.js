import test from "node:test";
import assert from "node:assert/strict";

import { groupTranscriptItems } from "../src/transcriptGroups.js";

test("anchors actions after the final assistant message", () => {
  const [group] = groupTranscriptItems([
    { id: "user-1", role: "user", text: "Show me" },
    { id: "assistant-1", role: "assistant", text: "First response" },
    { id: "tool-1", role: "tool", summary: "create visual" },
    {
      id: "assistant-2",
      role: "assistant",
      text: "Interrupted",
      status: "interrupted",
    },
  ]);

  assert.equal(group.actionAnchorId, "assistant-2");
});

test("does not anchor actions to a user message when no assistant exists", () => {
  const [group] = groupTranscriptItems([
    { id: "user-1", role: "user", text: "Show me" },
    { id: "tool-1", role: "tool", summary: "create visual" },
  ]);

  assert.equal(group.actionAnchorId, null);
});

test("keeps a late tool action with the assistant response that started it", () => {
  const groups = groupTranscriptItems([
    { id: "user-1", role: "user", text: "First request" },
    {
      id: "assistant-1",
      role: "assistant",
      responseId: "response-1",
      text: "First response",
    },
    { id: "user-2", role: "user", text: "Second request" },
    {
      id: "tool-1",
      role: "tool",
      responseId: "response-1",
      summary: "create visual",
    },
  ]);

  assert.equal(groups[0].actionAnchorId, "assistant-1");
  assert.deepEqual(groups[0].actions.map((item) => item.id), ["tool-1"]);
  assert.deepEqual(groups[1].actions, []);
});

test("groups multiple response generations and tools under their owning request", () => {
  const groups = groupTranscriptItems([
    { id: "user-1", role: "user", requestId: "request-1", text: "Explore" },
    { id: "assistant-1", role: "assistant", requestId: "request-1", responseId: "response-1", text: "Working" },
    { id: "tool-1", role: "tool", requestId: "request-1", responseId: "response-1", batchId: "batch-1" },
    { id: "assistant-2", role: "assistant", requestId: "request-1", responseId: "response-2", text: "Follow-up" },
    { id: "tool-2", role: "tool", requestId: "request-1", responseId: "response-2", batchId: "batch-2" },
    { id: "user-2", role: "user", requestId: "request-2", text: "Next" },
  ]);

  assert.equal(groups.length, 2);
  assert.deepEqual(groups[0].messages.map((item) => item.id), ["user-1", "assistant-1", "assistant-2"]);
  assert.deepEqual(groups[0].actions.map((item) => item.id), ["tool-1", "tool-2"]);
  assert.equal(groups[1].messages[0].id, "user-2");
});

test("request association wins while legacy items still fall back to response mapping", () => {
  const groups = groupTranscriptItems([
    { id: "user-1", role: "user", requestId: "request-1" },
    { id: "assistant-1", role: "assistant", requestId: "request-1", responseId: "response-1" },
    { id: "user-2", role: "user", requestId: "request-2" },
    { id: "tool-legacy", role: "tool", responseId: "response-1" },
    { id: "assistant-2", role: "assistant", requestId: "request-2", responseId: "response-2" },
    { id: "tool-request", role: "tool", requestId: "request-2", responseId: "response-1" },
  ]);
  assert.deepEqual(groups[0].actions.map((item) => item.id), ["tool-legacy"]);
  assert.deepEqual(groups[1].actions.map((item) => item.id), ["tool-request"]);
});
