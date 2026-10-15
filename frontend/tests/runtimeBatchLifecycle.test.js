import test from "node:test";
import assert from "node:assert/strict";
import { createPinia, setActivePinia } from "pinia";

import { useRuntimeStore } from "../src/stores/runtime.js";
import { SessionProjection } from "../src/sessionProjection.js";

test("only the active batch finalizer clears the tool-running state", () => {
  setActivePinia(createPinia());
  const runtime = useRuntimeStore();

  runtime.startToolBatch({ correlation: { batch_id: "batch-current" } });
  runtime.finishToolBatch({ correlation: { batch_id: "batch-stale" }, status: "revoked" });

  assert.equal(runtime.toolRunning, true);
  assert.equal(runtime.activeToolBatchId, "batch-current");

  runtime.finishToolBatch({ correlation: { batch_id: "batch-current" }, status: "failed" });

  assert.equal(runtime.toolRunning, false);
  assert.equal(runtime.activeToolBatchId, null);
});

test("an old batch cannot end a newer active batch", () => {
  setActivePinia(createPinia());
  const runtime = useRuntimeStore();
  runtime.startToolBatch({ batch_id: "new-batch" });
  assert.equal(runtime.finishToolBatch({ batch_id: "old-batch", status: "superseded" }), false);
  assert.equal(runtime.toolRunning, true);
  assert.equal(runtime.activeToolBatchId, "new-batch");
});

test("matching superseded batch terminal clears its own runtime loading through legacy projection", () => {
  setActivePinia(createPinia());
  const runtime = useRuntimeStore();
  const projection = new SessionProjection();
  assert(projection.accept({ type: "assistant_response_started", seq: 1, response_id: "response-old" }));
  assert(projection.accept({ type: "tool_execution_started", seq: 2, response_id: "response-old", batch_id: "batch-old" }));
  runtime.startToolBatch({ batch_id: "batch-old", tools: [{ name: "chart" }] });
  assert(projection.accept({ type: "revision_received", seq: 3, request_id: "request-new", previous_request_id: "request-old", previous_response_id: "response-old", revision_index: 1, previous_phase: "tool_execution", utterance_id: "u-new" }));
  assert(projection.accept({ type: "tool_execution_finished", seq: 4, response_id: "response-old", batch_id: "batch-old", status: "superseded", followup_requested: false }));

  assert.equal(runtime.finishToolBatch({ batch_id: "batch-old", status: "superseded", followup_requested: false }), true);
  assert.equal(runtime.toolRunning, false);
  assert.equal(runtime.activeToolBatchId, null);
  assert.equal(runtime.phase, "ready");
});

test("superseded old terminal leaves a newer runtime batch loading", () => {
  setActivePinia(createPinia());
  const runtime = useRuntimeStore();
  const projection = new SessionProjection();
  assert(projection.accept({ type: "assistant_response_started", seq: 1, response_id: "response-old" }));
  assert(projection.accept({ type: "tool_execution_started", seq: 2, response_id: "response-old", batch_id: "batch-old" }));
  runtime.startToolBatch({ batch_id: "batch-old" });
  assert(projection.accept({ type: "revision_received", seq: 3, request_id: "request-new", previous_request_id: "request-old", previous_response_id: "response-old", revision_index: 1, previous_phase: "tool_execution", utterance_id: "u-new" }));
  assert(projection.accept({ type: "assistant_response_started", seq: 4, response_id: "response-new" }));
  assert(projection.accept({ type: "tool_execution_started", seq: 5, response_id: "response-new", batch_id: "batch-new" }));
  runtime.startToolBatch({ batch_id: "batch-new", tools: [{ name: "new chart" }], changes_dashboard: true });
  assert(projection.accept({ type: "tool_execution_finished", seq: 6, response_id: "response-old", batch_id: "batch-old", status: "superseded", followup_requested: false }));

  assert.equal(runtime.finishToolBatch({ batch_id: "batch-old", status: "superseded", followup_requested: false }), false);
  assert.equal(runtime.toolRunning, true);
  assert.equal(runtime.activeToolBatchId, "batch-new");
  assert.equal(runtime.phase, "updating_dashboard");
});

test("a finish without an active exact batch is side-effect free", () => {
  setActivePinia(createPinia());
  const runtime = useRuntimeStore();
  assert.equal(runtime.finishToolBatch({ batch_id: "late-batch", status: "succeeded" }), false);
  assert.equal(runtime.toolRunning, false);
  assert.equal(runtime.phase, "connecting");
});

test("runtime dashboard state is dataset-neutral", () => {
  setActivePinia(createPinia());
  const runtime = useRuntimeStore();
  assert.equal(Object.hasOwn(runtime.dashboardState, "low_score_threshold"), false);
  runtime.updateDashboardState({ filters: [], views: [], chart_threshold: 9 });
  assert.equal(Object.hasOwn(runtime.dashboardState, "low_score_threshold"), false);
});

test("matching canonical terminal outcomes clear only their own loading state", () => {
  for (const commitStatus of ["read_only", "no_change", "superseded", "conflicted", "failed"]) {
    setActivePinia(createPinia());
    const runtime = useRuntimeStore();
    runtime.startToolBatch({ batch_id: "current", changes_dashboard: true });
    assert.equal(runtime.finishToolBatch({ batch_id: "older", commit_status: commitStatus, followup_requested: false }), false);
    assert.equal(runtime.toolRunning, true);
    assert.equal(runtime.finishToolBatch({ batch_id: "current", commit_status: commitStatus, followup_requested: false }), true);
    assert.equal(runtime.toolRunning, false);
    assert.equal(runtime.phase, "ready");
  }
});

test("canonical execution failure overrides legacy per-call success in runtime feedback", () => {
  setActivePinia(createPinia());
  const runtime = useRuntimeStore();
  runtime.recordToolResult({ success: true, execution_status: "failed", commit_status: "failed", error: { message: "Rolled back" } });
  assert.equal(runtime.lastToolError, "Rolled back");
});
