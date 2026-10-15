export async function applyRrtEffects(effects = [], dependencies = {}) {
  const acknowledgements = [];
  for (const effect of effects) {
    if (effect.type === "dashboard_commit") {
      const acknowledgement = await applyDashboardCommit(effect, dependencies);
      if (acknowledgement) acknowledgements.push(acknowledgement);
      continue;
    }
    applyRuntimeEffect(effect, dependencies);
  }
  return acknowledgements;
}

export function createProjectionAck(envelope, {
  startedAt,
  completedAt,
} = {}) {
  return {
    type: "dashboard_projection_ack",
    ack_stage: "state_projected",
    seq: envelope.seq,
    batch_id: envelope.correlation.batch_id,
    revision: envelope.payload.revision,
    snapshot_digest: envelope.payload.snapshot_digest,
    client_monotonic_latency_ms: Math.max(0, completedAt - startedAt),
  };
}

async function applyDashboardCommit(effect, dependencies) {
  const { dashboard, runtime, nextTick = () => Promise.resolve(), sendAck, now = monotonicNow } = dependencies;
  if (!dashboard?.applyDashboardCommit) return null;
  const startedAt = now();
  const applied = dashboard.applyDashboardCommit({
    viewList: effect.snapshot.views || [],
    state: effect.snapshot,
    revision: effect.revision,
    digest: effect.digest,
  });
  if (!applied) return null;
  runtime?.updateDashboardState?.(effect.snapshot);
  await nextTick();
  const acknowledgement = createProjectionAck(effect.envelope, {
    startedAt,
    completedAt: now(),
  });
  sendAck?.(acknowledgement);
  return acknowledgement;
}

function applyRuntimeEffect(effect, { dashboard, runtime } = {}) {
  if (effect.type === "tool_call") {
    dashboard?.addToolItem?.({
      name: effect.event.name,
      arguments: effect.event.arguments,
      summary: effect.event.contract?.label,
      callId: effect.event.call_id || effect.correlation.call_id,
      batchId: effect.correlation.batch_id,
      cardKey: effect.cardKey,
      responseId: effect.correlation.response_id,
    });
    return;
  }
  if (effect.type === "tool_result") {
    const message = {
      ...effect.event,
      correlation: effect.correlation,
      batch_id: effect.correlation.batch_id,
      call_id: effect.event.call_id || effect.correlation.call_id,
    };
    dashboard?.handleToolResult?.(message);
    runtime?.recordToolResult?.(message);
    return;
  }
  if (effect.type === "tool_execution_started") {
    runtime?.startToolBatch?.({ ...effect.event, correlation: effect.correlation });
    return;
  }
  if (effect.type === "tool_execution_finished") {
    if (effect.event.fatal_error) {
      dashboard?.failRunningToolItems?.(effect.correlation.response_id, effect.event.fatal_error);
    }
    runtime?.finishToolBatch?.({ ...effect.event, correlation: effect.correlation });
  }
}

function monotonicNow() {
  return globalThis.performance?.now?.() ?? Date.now();
}
