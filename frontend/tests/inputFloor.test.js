import test from "node:test";
import assert from "node:assert/strict";
import { createPinia, setActivePinia } from "pinia";
import { useRuntimeStore } from "../src/stores/runtime.js";
import * as policy from "../src/realtimePolicy.js";

const input = (seq, accepts_audio, phase = "ready", condition = "turn_taking") => ({
  type: "input_policy", seq, accepts_audio, phase, condition,
});

test("server floor stays closed through local playback idle and stale reopen", () => {
  setActivePinia(createPinia());
  const runtime = useRuntimeStore();
  assert.equal(runtime.acceptsAudio, false);
  runtime.applyInputPolicy(input(1, true));
  runtime.applyInputPolicy(input(3, false, "tool_executing"));
  runtime.setPhase("ready");
  assert.equal(runtime.acceptsAudio, false);
  assert.equal(runtime.applyInputPolicy(input(2, true)), false);
  assert.equal(runtime.applyInputPolicy(input(3, true)), false);
  assert.equal(runtime.acceptsAudio, false);
  assert.equal(runtime.applyInputPolicy(input(4, true)), true);
  assert.equal(runtime.acceptsAudio, true);
});

test("malformed control updates cannot consume sequence or open input", () => {
  setActivePinia(createPinia());
  const runtime = useRuntimeStore();
  for (const malformed of [input(1, "true"), input(1, true, "invented"), input(1, true, "ready", "unknown"), input(1, true, "ready", "half_duplex"), input(1.5, true)]) {
    assert.equal(runtime.applyInputPolicy(malformed), false);
  }
  assert.equal(runtime.acceptsAudio, false);
  assert.equal(runtime.applyInputPolicy(input(1, true)), true);
  runtime.resetRuntime();
  assert.equal(runtime.acceptsAudio, false);
  assert.equal(runtime.applyInputPolicy(input(1, true)), true);
});

test("audio forwarding requires authoritative floor even with idle playback", () => {
  const ready = { sessionReady: true, acceptsAudio: true, captureBlocked: false, socketOpen: true };
  assert.equal(policy.canTransmitAudio(ready), true);
  for (const closed of [{ acceptsAudio: false }, { sessionReady: false }, { captureBlocked: true }, { socketOpen: false }]) {
    assert.equal(policy.canTransmitAudio({ ...ready, ...closed }), false);
  }
});

test("recording mic always remains stoppable while turn-taking waits", () => {
  const state = { recording: true, starting: false, sessionReady: true, connected: true, captureBlocked: false, acceptsAudio: false };
  assert.equal(policy.microphoneControl(state).disabled, false);
  assert.match(policy.microphoneControl(state).label, /paused/i);
  assert.equal(policy.microphoneControl({ ...state, sessionReady: false, connected: false }).disabled, false);
  assert.equal(policy.microphoneControl({ ...state, recording: false }).disabled, true);
});

test("revision-enabled can start capture during tool execution when server accepts audio", () => {
  const control = policy.microphoneControl({ recording: false, starting: false, sessionReady: true, connected: true, captureBlocked: false, acceptsAudio: true, toolRunning: true });
  assert.equal(control.disabled, false);
  assert.match(control.label, /start/i);
});
