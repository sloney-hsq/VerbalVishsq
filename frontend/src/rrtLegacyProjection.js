export function projectLegacyEvents(message = {}, project) {
  const events = Array.isArray(message.legacy_events)
    ? message.legacy_events
    : [message];
  for (const event of events) project(event);
}

export function legacyToolItemPayload(message = {}) {
  const batchId = message.correlation?.batch_id || message.batch_id || null;
  const callId = message.call_id || null;
  return {
    name: message.name,
    arguments: message.arguments,
    summary: message.contract?.label,
    callId,
    batchId,
    cardKey: batchId && callId ? `${batchId}:${callId}` : null,
    responseId: message.response_id,
    requestId: message.request_id || null,
  };
}
