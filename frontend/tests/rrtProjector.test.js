import test from "node:test";
import assert from "node:assert/strict";

import {
  isVersionedRrtMessage,
  validateRrtEnvelope,
} from "../src/protocol/rrtContract.js";
import {
  createRrtProjectionState,
  projectRrtEvent,
} from "../src/protocol/rrtProjector.js";
import {
  applyRrtEffects,
  createProjectionAck,
} from "../src/protocol/rrtEffects.js";

function envelope(overrides = {}) {
  const {
    correlation: correlationOverrides = {},
    payload: payloadOverrides = {},
    ...rest
  } = overrides;
  const correlation = {
    session_id: "session-1",
    trial_id: "trial-1",
    condition: "revision_enabled",
    intent_epoch: 2,
    response_id: "response-1",
    base_revision: 7,
    batch_id: "batch-1",
    call_id: null,
    ...correlationOverrides,
  };
  return {
    protocol: "verbalvis.rrt",
    version: 1,
    seq: 42,
    event: "dashboard_commit",
    correlation,
    commit_status: "committed",
    ...rest,
    payload: {
      revision: 8,
      snapshot: { views: [{ id: "v1" }] },
      snapshot_digest: "sha256:revision-8",
      ...payloadOverrides,
    },
    correlation,
  };
}

test("validates the exact versioned envelope and rejects malformed correlation", () => {
  const valid = validateRrtEnvelope(envelope());
  assert.equal(valid.ok, true);

  const invalid = validateRrtEnvelope(envelope({
    correlation: { batch_id: undefined },
  }));
  assert.deepEqual(invalid, {
    ok: false,
    reason: "invalid_correlation.batch_id",
  });

  assert.deepEqual(validateRrtEnvelope(envelope({ event: "unknown" })), {
    ok: false,
    reason: "invalid_event",
  });
  assert.deepEqual(validateRrtEnvelope(envelope({ correlation: { condition: "full_duplex_rrt" } })), {
    ok: false,
    reason: "invalid_correlation.condition",
  });
});

test("routes only protocol-labelled frames through the RRT projector so legacy fallback remains available", () => {
  assert.equal(isVersionedRrtMessage(envelope()), true);
  assert.equal(isVersionedRrtMessage({ type: "dashboard_commit" }), false);
});

test("projects committed revision 8 once and ignores duplicate sequence 42 and stale 41", () => {
  const first = projectRrtEvent(createRrtProjectionState(), envelope());
  assert.equal(first.accepted, true);
  assert.equal(first.state.dashboard.revision, 8);
  assert.equal(first.effects.filter((effect) => effect.type === "dashboard_commit").length, 1);

  const duplicate = projectRrtEvent(first.state, envelope());
  assert.equal(duplicate.accepted, false);
  assert.equal(duplicate.reason, "duplicate_or_stale_seq");
  assert.deepEqual(duplicate.effects, []);

  const stale = projectRrtEvent(first.state, envelope({ seq: 41 }));
  assert.equal(stale.accepted, false);
  assert.equal(stale.reason, "duplicate_or_stale_seq");
  assert.deepEqual(stale.effects, []);
});

test("does not project a revoked snapshot into the dashboard", () => {
  const projected = projectRrtEvent(
    createRrtProjectionState(),
    envelope({ commit_status: "revoked" }),
  );

  assert.equal(projected.accepted, true);
  assert.equal(projected.state.dashboard.revision, -1);
  assert.deepEqual(projected.effects.filter((effect) => effect.type === "dashboard_commit"), []);
});

test("validated non-committed dashboard envelopes advance anti-replay only", () => {
  for (const status of ["read_only", "revoked", "failed", "conflicted"]) {
    const projected = projectRrtEvent(
      createRrtProjectionState(),
      envelope({ commit_status: status }),
    );
    assert.equal(projected.accepted, true, status);
    assert.equal(projected.reason, "non_authoritative_status", status);
    assert.equal(projected.state.sessions["session-1"].lastSeq, 42, status);
    assert.equal(projected.state.dashboard.revision, -1, status);
    assert.deepEqual(projected.effects, [], status);
  }
});

test("rejects malformed snapshots without consuming their sequence", () => {
  const rejected = projectRrtEvent(createRrtProjectionState(), envelope({
    payload: { snapshot: { views: {} } },
  }));
  assert.equal(rejected.accepted, false);
  assert.equal(rejected.reason, "invalid_payload.snapshot.views");
  assert.equal(rejected.state.sessions["session-1"], undefined);

  const accepted = projectRrtEvent(rejected.state, envelope());
  assert.equal(accepted.accepted, true);
  assert.equal(accepted.state.dashboard.revision, 8);
  assert.deepEqual(validateRrtEnvelope(envelope({
    payload: { snapshot: { views: [], filters: {} } },
  })), { ok: false, reason: "invalid_payload.snapshot.filters" });
});

test("keys tool cards by batch and call so reused call IDs remain distinct", () => {
  const first = projectRrtEvent(createRrtProjectionState(), envelope({
    legacy_events: [{ type: "tool_call", call_id: "call-1", name: "first" }],
  }));
  const second = projectRrtEvent(first.state, envelope({
    seq: 43,
    correlation: { batch_id: "batch-2" },
    legacy_events: [{ type: "tool_call", call_id: "call-1", name: "second" }],
  }));

  assert.deepEqual(Object.keys(second.state.toolCards).sort(), [
    "batch-1:call-1",
    "batch-2:call-1",
  ]);
});

test("rejects an equal revision with a different digest without dashboard effects", () => {
  const first = projectRrtEvent(createRrtProjectionState(), envelope());
  const conflicting = projectRrtEvent(first.state, envelope({
    seq: 43,
    payload: { snapshot_digest: "sha256:different" },
  }));

  assert.equal(conflicting.accepted, false);
  assert.equal(conflicting.reason, "conflicting_revision_digest");
  assert.deepEqual(conflicting.effects.filter((effect) => effect.type === "dashboard_commit"), []);
});

test("projects combined compatibility events in wire order but applies the dashboard once", () => {
  const projected = projectRrtEvent(createRrtProjectionState(), envelope({
    legacy_events: [
      { type: "tool_call", call_id: "call-1", name: "select" },
      { type: "dashboard_commit", dashboard_revision: 8 },
      { type: "tool_result", call_id: "call-1", success: true },
      { type: "tool_execution_finished", status: "succeeded" },
    ],
  }));

  assert.deepEqual(projected.effects.map((effect) => effect.type), [
    "tool_call",
    "dashboard_commit",
    "tool_result",
    "tool_execution_finished",
  ]);
  assert.equal(projected.effects.filter((effect) => effect.type === "dashboard_commit").length, 1);
});

test("deduplicates repeated embedded tool calls and results by batch and call", () => {
  const projected = projectRrtEvent(createRrtProjectionState(), envelope({
    legacy_events: [
      { type: "tool_call", call_id: "call-1", name: "select" },
      { type: "tool_call", call_id: "call-1", name: "select" },
      { type: "dashboard_commit", dashboard_revision: 8 },
      { type: "tool_result", call_id: "call-1", success: true },
      { type: "tool_result", call_id: "call-1", success: true },
    ],
  }));

  assert.deepEqual(projected.effects.map((effect) => effect.type), [
    "tool_call",
    "dashboard_commit",
    "tool_result",
  ]);
  assert.equal(Object.keys(projected.state.toolCards).length, 1);
  assert.equal(projected.state.toolCards["batch-1:call-1"].status, "completed");
});

test("effects acknowledge only after projection and never grant dashboard authority", async () => {
  const projected = projectRrtEvent(createRrtProjectionState(), envelope());
  const timeline = [];
  const sent = [];
  const dashboard = {
    applyDashboardCommit(commit) {
      timeline.push(["commit", commit.revision]);
      return true;
    },
  };
  const runtime = {
    updateDashboardState() { timeline.push(["runtime"]); },
  };

  await applyRrtEffects(projected.effects, {
    dashboard,
    runtime,
    nextTick: async () => timeline.push(["nextTick"]),
    now: (() => { let time = 100; return () => time += 5; })(),
    sendAck: (ack) => { timeline.push(["ack"]); sent.push(ack); },
  });

  assert.deepEqual(timeline.map(([kind]) => kind), ["commit", "runtime", "nextTick", "ack"]);
  assert.deepEqual(sent[0], {
    type: "dashboard_projection_ack",
    ack_stage: "state_projected",
    seq: 42,
    batch_id: "batch-1",
    revision: 8,
    snapshot_digest: "sha256:revision-8",
    client_monotonic_latency_ms: 5,
  });
  assert.equal(validateRrtEnvelope(sent[0]).ok, false);
  assert.equal(projected.state.dashboard.revision, 8);
});

test("projection ACK has no render-completion variant", () => {
  assert.deepEqual(createProjectionAck(envelope(), {
    startedAt: 10,
    completedAt: 12,
  }), {
    type: "dashboard_projection_ack",
    ack_stage: "state_projected",
    seq: 42,
    batch_id: "batch-1",
    revision: 8,
    snapshot_digest: "sha256:revision-8",
    client_monotonic_latency_ms: 2,
  });
});
