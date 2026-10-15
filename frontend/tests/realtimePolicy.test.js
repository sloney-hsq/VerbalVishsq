import test from "node:test";
import assert from "node:assert/strict";

import {
  captureBlockedForPlaybackStop,
  conditionFromSearch,
  withExperimentContext,
  withStudyCondition,
} from "../src/realtimePolicy.js";

test("speech overlap stops playback without blocking microphone capture", () => {
  assert.equal(captureBlockedForPlaybackStop("speech_overlap"), false);
  assert.equal(captureBlockedForPlaybackStop("user_interruption"), true);
});

test("page query aliases normalize before WebSocket projection", () => {
  assert.equal(conditionFromSearch("?condition=turn_taking"), "turn_taking");
  assert.equal(conditionFromSearch("?condition=revision_enabled"), "revision_enabled");
  assert.equal(conditionFromSearch("?condition=half_duplex"), "turn_taking");
  assert.equal(
    conditionFromSearch("?condition=full_duplex_rrt"),
    "revision_enabled",
  );
  assert.equal(conditionFromSearch("?condition=other"), null);
  assert.equal(
    withStudyCondition("ws://localhost/ws?analysis_id=a", "?condition=half_duplex"),
    "ws://localhost/ws?analysis_id=a&condition=turn_taking",
  );
});

test("pilot page context is allowlisted into the backend WebSocket URL", () => {
  const projected = withExperimentContext(
    "ws://localhost/ws?analysis_id=a&participant_id=stale",
    "?condition=full_duplex_rrt&participant_id=P-007&trial_id=P-007.t1" +
      "&task_id=delivery-investigation&dataset_id=olist&ws=ignored&secret=ignored",
  );
  const url = new URL(projected);

  assert.deepEqual(Object.fromEntries(url.searchParams), {
    analysis_id: "a",
    participant_id: "P-007",
    condition: "revision_enabled",
    trial_id: "P-007.t1",
    task_id: "delivery-investigation",
    dataset_id: "olist",
  });
});
