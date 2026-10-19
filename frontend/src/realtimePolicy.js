const STUDY_CONDITIONS = new Set(["turn_taking", "revision_enabled"]);
const INGRESS_ALIASES = new Map([
  ["half_duplex", "turn_taking"],
  ["full_duplex_rrt", "revision_enabled"],
]);
const INPUT_PHASES = new Set([
  "ready", "assistant_streaming", "tool_executing", "followup_generating",
  "connecting", "configuration_error", "disconnected", "error", "closed",
]);

export function validInputPolicy(message, previousSeq) {
  return message?.type === "input_policy" &&
    Number.isSafeInteger(message.seq) && message.seq > previousSeq &&
    STUDY_CONDITIONS.has(message.condition) && INPUT_PHASES.has(message.phase) &&
    typeof message.accepts_audio === "boolean";
}

export function canTransmitAudio({ sessionReady, acceptsAudio, captureBlocked, socketOpen }) {
  return sessionReady === true && acceptsAudio === true && !captureBlocked && socketOpen === true;
}

export function microphoneControl({ recording, starting, sessionReady, connected, captureBlocked, acceptsAudio }) {
  // Stopping local capture is always available, even after a disconnect or floor loss.
  if (recording) return {
    disabled: false,
    label: acceptsAudio && sessionReady && connected && !captureBlocked
      ? "Listening · Stop mic" : "Mic paused · Stop mic",
  };
  if (starting) return { disabled: true, label: "Starting" };
  if (!connected || !sessionReady) return { disabled: true, label: "Mic unavailable" };
  if (!acceptsAudio || captureBlocked) return { disabled: true, label: "Please wait" };
  return { disabled: false, label: "Start mic" };
}

export function studyVoiceControl({ phase }) {
  const exploring = phase === 'exploring';
  return { microphoneEnabled: exploring, stopEnabled: exploring };
}

export function captureBlockedForPlaybackStop(reason) {
  return reason !== "speech_overlap";
}

export function conditionFromSearch(search) {
  const condition = new URLSearchParams(search).get("condition");
  return STUDY_CONDITIONS.has(condition) ? condition : INGRESS_ALIASES.get(condition) || null;
}

export function withStudyCondition(urlValue, search) {
  return withExperimentContext(urlValue, search);
}

export function withExperimentContext(urlValue, search) {
  const url = new URL(urlValue);
  const source = new URLSearchParams(search);
  const condition = conditionFromSearch(source);
  if (condition) url.searchParams.set("condition", condition);
  for (const field of ["participant_id", "trial_id", "task_id", "dataset_id"]) {
    if (source.has(field)) url.searchParams.set(field, source.get(field));
  }
  return url.toString();
}
