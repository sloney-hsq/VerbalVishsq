import { validateRrtEnvelope } from "./rrtContract.js";

export function createRrtProjectionState() {
  return {
    sessions: {},
    dashboard: { revision: -1, digest: null, snapshot: null },
    toolCards: {},
  };
}

export function projectRrtEvent(previousState, rawEvent) {
  const validation = validateRrtEnvelope(rawEvent);
  const state = normalizeState(previousState);
  if (!validation.ok) return rejected(state, validation.reason);

  const event = validation.value;
  const sessionId = event.correlation.session_id;
  const lastSeq = state.sessions[sessionId]?.lastSeq || 0;
  if (event.seq <= lastSeq) return rejected(state, "duplicate_or_stale_seq");

  const next = withSequence(state, sessionId, event.seq);
  const decision = dashboardDecision(next.dashboard, event);
  if (decision.rejectReason) return rejected(next, decision.rejectReason);
  if (decision.reason === "non_authoritative_status") {
    return { state: next, effects: [], accepted: true, reason: decision.reason };
  }

  if (decision.nextDashboard) next.dashboard = decision.nextDashboard;
  const dashboardEffect = decision.apply
    ? dashboardCommitEffect(event)
    : null;
  const effects = compatibilityEffects(next, event, dashboardEffect);

  return {
    state: next,
    effects,
    accepted: true,
    reason: decision.reason,
  };
}

function normalizeState(state) {
  const source = state && typeof state === "object" ? state : createRrtProjectionState();
  return {
    sessions: { ...(source.sessions || {}) },
    dashboard: {
      revision: Number.isSafeInteger(source.dashboard?.revision)
        ? source.dashboard.revision
        : -1,
      digest: source.dashboard?.digest || null,
      snapshot: source.dashboard?.snapshot || null,
    },
    toolCards: { ...(source.toolCards || {}) },
  };
}

function withSequence(state, sessionId, seq) {
  return {
    ...state,
    sessions: {
      ...state.sessions,
      [sessionId]: { ...(state.sessions[sessionId] || {}), lastSeq: seq },
    },
  };
}

function dashboardDecision(dashboard, event) {
  if (event.event !== "dashboard_commit" || event.commit_status !== "committed") {
    return { apply: false, reason: "non_authoritative_status" };
  }
  const revision = event.payload.revision;
  const digest = event.payload.snapshot_digest;
  if (revision > dashboard.revision) {
    return {
      apply: true,
      reason: null,
      nextDashboard: { revision, digest, snapshot: event.payload.snapshot },
    };
  }
  if (revision === dashboard.revision && digest === dashboard.digest) {
    return { apply: false, reason: "idempotent_revision" };
  }
  return {
    apply: false,
    rejectReason: revision === dashboard.revision
      ? "conflicting_revision_digest"
      : "stale_dashboard_revision",
  };
}

function compatibilityEffects(state, event, dashboardEffect) {
  const legacyEvents = Array.isArray(event.legacy_events) ? event.legacy_events : null;
  if (!legacyEvents) return dashboardEffect ? [dashboardEffect] : [];

  const effects = [];
  const seenToolEffects = new Set();
  let dashboardPlaced = false;
  for (const legacyEvent of legacyEvents) {
    const type = legacyEvent?.type;
    if (type === "dashboard_commit") {
      if (dashboardEffect && !dashboardPlaced) {
        effects.push(dashboardEffect);
        dashboardPlaced = true;
      } else {
        effects.push({ type: "dashboard_ignored", event: legacyEvent });
      }
      continue;
    }
    const key = legacyToolEffectKey(event, legacyEvent);
    if (key && seenToolEffects.has(key)) continue;
    if (key) seenToolEffects.add(key);
    const effect = legacyEffect(state, event, legacyEvent);
    if (effect) effects.push(effect);
  }
  if (dashboardEffect && !dashboardPlaced) effects.push(dashboardEffect);
  return effects;
}

function legacyToolEffectKey(envelope, event) {
  if (event?.type !== "tool_call" && event?.type !== "tool_result") return null;
  const correlation = { ...envelope.correlation, ...(event.correlation || {}) };
  const callId = event.call_id || correlation.call_id;
  const cardKey = toolCardKey(correlation.batch_id, callId);
  return cardKey ? `${event.type}:${cardKey}` : null;
}

function legacyEffect(state, envelope, event) {
  const correlation = {
    ...envelope.correlation,
    ...(event?.correlation || {}),
  };
  const type = event?.type;
  if (type === "tool_call") {
    const callId = event.call_id || correlation.call_id;
    const batchId = correlation.batch_id;
    const cardKey = toolCardKey(batchId, callId);
    if (cardKey) {
      state.toolCards[cardKey] = {
        key: cardKey,
        batchId,
        callId,
        status: "running",
      };
    }
    return { type, event, correlation, cardKey };
  }
  if (type === "tool_result") {
    const callId = event.call_id || correlation.call_id;
    const cardKey = toolCardKey(correlation.batch_id, callId);
    if (cardKey && state.toolCards[cardKey]) {
      state.toolCards[cardKey] = {
        ...state.toolCards[cardKey],
        status: event.success === false ? "error" : "completed",
      };
    }
    return { type, event, correlation, cardKey };
  }
  if (type === "tool_execution_started" || type === "tool_execution_finished") {
    return { type, event, correlation };
  }
  return { type: "legacy_event", event, correlation };
}

function dashboardCommitEffect(event) {
  return {
    type: "dashboard_commit",
    envelope: event,
    revision: event.payload.revision,
    digest: event.payload.snapshot_digest,
    snapshot: event.payload.snapshot,
  };
}

function toolCardKey(batchId, callId) {
  return typeof batchId === "string" && batchId && typeof callId === "string" && callId
    ? `${batchId}:${callId}`
    : null;
}

function rejected(state, reason) {
  return { state, effects: [], accepted: false, reason };
}
