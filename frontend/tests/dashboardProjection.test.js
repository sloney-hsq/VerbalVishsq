import test from "node:test";
import assert from "node:assert/strict";
import { createPinia, setActivePinia } from "pinia";

import { useDashboardStore } from "../src/stores/dashboard.js";
import { legacyToolItemPayload } from "../src/rrtLegacyProjection.js";
import { useRuntimeStore } from '../src/stores/runtime.js';

test('structured tool errors show their message, not object conversion', () => {
  setActivePinia(createPinia());
  const dashboard = useDashboardStore(), runtime = useRuntimeStore();
  dashboard.addToolItem({callId:'c',batchId:'b',name:'create_chart'});
  const result = {call_id:'c',batch_id:'b',success:false,error:{code:'tool_error',message:'Missing column'}};
  dashboard.handleToolResult(result);
  runtime.recordToolResult(result);
  assert.equal(dashboard.transcriptItems[0].error, 'Missing column');
  assert.equal(runtime.lastToolError, 'Missing column');
});

test("dashboard accepts only newer revisions or an exact digest replay", () => {
  setActivePinia(createPinia());
  const dashboard = useDashboardStore();

  assert.equal(dashboard.applyDashboardCommit({
    viewList: [{ id: "revision-8" }],
    state: {},
    revision: 8,
    digest: "sha256:8",
  }), true);
  assert.equal(dashboard.applyDashboardCommit({
    viewList: [{ id: "wrong-content" }],
    state: {},
    revision: 8,
    digest: "sha256:other",
  }), false);
  assert.equal(dashboard.applyDashboardCommit({
    viewList: [{ id: "old" }],
    state: {},
    revision: 7,
    digest: "sha256:7",
  }), false);
  assert.equal(dashboard.applyDashboardCommit({
    viewList: [{ id: "revision-8" }],
    state: {},
    revision: 8,
    digest: "sha256:8",
  }), true);
  assert.equal(dashboard.views[0].id, "revision-8");
});

test("tool cards with a shared call ID stay distinct across batches", () => {
  setActivePinia(createPinia());
  const dashboard = useDashboardStore();

  dashboard.addToolItem({ callId: "call-1", batchId: "batch-a", name: "one" });
  dashboard.addToolItem({ callId: "call-1", batchId: "batch-b", name: "two" });
  dashboard.handleToolResult({
    call_id: "call-1",
    batch_id: "batch-b",
    success: true,
  });

  const cards = dashboard.transcriptItems.filter((item) => item.role === "tool");
  assert.deepEqual(cards.map((item) => item.cardKey), ["batch-a:call-1", "batch-b:call-1"]);
  assert.deepEqual(cards.map((item) => item.status), ["running", "completed"]);
});

test("legacy tool calls retain their batch key through the matching result", () => {
  setActivePinia(createPinia());
  const dashboard = useDashboardStore();
  const toolCall = {
    type: "tool_call",
    call_id: "call-1",
    name: "select",
    correlation: { batch_id: "batch-compat" },
  };

  dashboard.addToolItem(legacyToolItemPayload(toolCall));
  dashboard.handleToolResult({
    call_id: "call-1",
    batch_id: "batch-compat",
    success: true,
  });

  const cards = dashboard.transcriptItems.filter((item) => item.role === "tool");
  assert.equal(cards.length, 1);
  assert.equal(cards[0].cardKey, "batch-compat:call-1");
  assert.equal(cards[0].status, "completed");
  assert.equal(cards.some((item) => item.status === "running"), false);
  assert.equal(legacyToolItemPayload({
    call_id: "call-fallback",
    batch_id: "batch-plain",
  }).cardKey, "batch-plain:call-fallback");
});

test("revision feedback annotates its own transcript request without altering committed charts", () => {
  setActivePinia(createPinia());
  const dashboard = useDashboardStore();
  dashboard.initViews([{ id: "committed-chart" }], 7, {});
  const accepted = dashboard.completeUserTranscript("Revise this", { utteranceId: "u-new", requestId: "request-new" });
  dashboard.acceptRevision("request-new");
  const oldAssistant = dashboard.appendAssistantTranscript("response-old", "Old answer", "request-old");
  dashboard.beginAssistantResponse("response-new", "request-new");
  const oldTool = dashboard.addToolItem({ callId: "call-old", batchId: "batch-old", responseId: "response-old", requestId: "request-old", name: "chart" });

  dashboard.markRequestSuperseded("request-old", "response-old");
  dashboard.finishSupersededBatch("batch-old");

  assert.equal(accepted.revisionAccepted, true);
  assert.equal(oldAssistant.superseded, true);
  assert.equal(oldTool.status, "superseded");
  assert.equal(dashboard.dashboardRevision, 7);
  assert.deepEqual(dashboard.views.map((view) => view.id), ["committed-chart"]);
});

test("revision acceptance arriving before its user transcript is retained", () => {
  setActivePinia(createPinia());
  const dashboard = useDashboardStore();
  dashboard.acceptRevision("request-new");
  const user = dashboard.completeUserTranscript("Revise this", {
    utteranceId: "u-new",
    requestId: "request-new",
  });
  assert.equal(user.revisionAccepted, true);
});

test("superseded batch status only updates matching tool cards", () => {
  setActivePinia(createPinia());
  const dashboard = useDashboardStore();
  const oldCard = dashboard.addToolItem({ callId: "same", batchId: "old", name: "old" });
  const newCard = dashboard.addToolItem({ callId: "same", batchId: "new", name: "new" });
  dashboard.finishSupersededBatch("old");
  assert.equal(oldCard.status, "superseded");
  assert.equal(newCard.status, "running");
});

test("non-committing terminal outcomes preserve committed views and settle matching cards", () => {
  for (const commitStatus of ["read_only", "no_change", "superseded", "conflicted", "failed"]) {
    setActivePinia(createPinia());
    const dashboard = useDashboardStore();
    dashboard.initViews([{ id: "committed-chart" }], 7, {});
    const oldCard = dashboard.addToolItem({ callId: "old", batchId: "old-batch", name: "chart" });
    const currentCard = dashboard.addToolItem({ callId: "current", batchId: "current-batch", name: "chart" });
    dashboard.finishTerminalBatch("current-batch", commitStatus);
    assert.equal(oldCard.status, "running");
    assert.equal(currentCard.status, commitStatus === "superseded" ? "superseded" :
      commitStatus === "failed" || commitStatus === "conflicted" ? "error" : "completed");
    assert.equal(dashboard.dashboardRevision, 7);
    assert.deepEqual(dashboard.views.map((view) => view.id), ["committed-chart"]);
  }
});

test("canonical tool result records outcome independently of legacy success", () => {
  setActivePinia(createPinia());
  const dashboard = useDashboardStore();
  const card = dashboard.addToolItem({ callId: "c", batchId: "b", name: "inspect_dashboard" });
  dashboard.handleToolResult({ call_id: "c", batch_id: "b", success: true,
    execution_status: "succeeded", commit_status: "read_only", state_changed: false });
  assert.equal(card.status, "completed");
  assert.equal(card.commitStatus, "read_only");
  assert.equal(card.stateChanged, false);
});
