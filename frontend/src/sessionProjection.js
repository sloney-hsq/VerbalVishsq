/** Defensive wire projection; it does not decide whether backend work may commit. */
export class SessionProjection {
  constructor() {
    this.seq = 0;
    this.revision = -1;
    this.current = null;
    this.revoked = new Set();
    this.batches = new Map();
    this.cards = new Set();
    this.revisions = new Set();
    this.supersessions = new Set();
    this.finishedBatches = new Set();
  }
  accept(message) {
    if (['configuration_error', 'error'].includes(message.type) && message.seq == null) return true;
    if (!Number.isSafeInteger(message.seq) || message.seq <= this.seq) return false;
    const {type, response_id: rid, batch_id: batch} = message;
    if (type === 'revision_received' && !validRevisionReceived(message)) return false;
    if (type === 'response_superseded' && !validResponseSuperseded(message)) return false;
    this.seq = message.seq;
    if (type === 'init') {
      this.revision = message.dashboard_revision;
      return Number.isSafeInteger(this.revision);
    }
    if (type === 'assistant_playback_stop') {
      if (rid) this.revoked.add(rid);
      if (rid === this.current) this.current = null;
      return true;
    }
    if (type === 'revision_received') {
      if (!message.request_id || this.revisions.has(message.request_id)) return false;
      rememberBounded(this.revisions, message.request_id, 512);
      if (message.previous_response_id) this.revoked.add(message.previous_response_id);
      return true;
    }
    if (type === 'response_superseded') {
      const key = `${message.request_id || ''}:${rid || ''}`;
      if ((!message.request_id && !rid) || this.supersessions.has(key)) return false;
      rememberBounded(this.supersessions, key, 512);
      if (rid) this.revoked.add(rid);
      if (rid === this.current) this.current = null;
      return true;
    }
    if (rid && this.revoked.has(rid) && type !== 'tool_execution_finished') return false;
    if (type === 'tool_execution_finished') {
      const knownBatch = batch && this.batches.get(batch) === rid;
      if (!knownBatch || this.finishedBatches.has(batch)) return false;
      const supersededTerminal = message.status === 'superseded' && rid && this.revoked.has(rid);
      if (rid && this.revoked.has(rid) && !supersededTerminal) return false;
      rememberBounded(this.finishedBatches, batch, 256);
      return true;
    }
    if (type === 'assistant_response_started') {
      if (this.current && this.current !== rid) this.revoked.add(this.current);
      this.current = rid;
    }
    if (type === 'tool_execution_started') {
      if (!rid || rid !== this.current || !batch || this.batches.has(batch)) return false;
      this.batches.set(batch, rid);
    }
    if (['dashboard_commit', 'tool_call', 'tool_result'].includes(type)) {
      if (!batch || this.batches.get(batch) !== rid || rid !== this.current) return false;
      if (type === 'dashboard_commit') {
        if (!Number.isSafeInteger(message.dashboard_revision) || message.dashboard_revision <= this.revision) return false;
        this.revision = message.dashboard_revision;
      } else {
        const key = `${type}:${batch}:${message.call_id}`;
        if (!message.call_id || this.cards.has(key)) return false;
        this.cards.add(key);
      }
    }
    // Session records are bounded, and unknown old batches are denied.
    while (this.batches.size > 256) this.batches.delete(this.batches.keys().next().value);
    while (this.revoked.size > 512) this.revoked.delete(this.revoked.values().next().value);
    while (this.cards.size > 4096) this.cards.delete(this.cards.values().next().value);
    while (this.revisions.size > 512) this.revisions.delete(this.revisions.values().next().value);
    while (this.supersessions.size > 512) this.supersessions.delete(this.supersessions.values().next().value);
    while (this.finishedBatches.size > 256) this.finishedBatches.delete(this.finishedBatches.values().next().value);
    return true;
  }
}

function rememberBounded(set, value, limit) {
  set.add(value);
  while (set.size > limit) set.delete(set.values().next().value);
}

const ACTIVE_REQUEST_PHASES = new Set(['reasoning', 'tool_execution', 'committing', 'speaking']);

function nonEmptyString(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function nullableNonEmptyString(value) {
  return value === null || nonEmptyString(value);
}

function validRevisionReceived(message) {
  return nonEmptyString(message.request_id) &&
    nonEmptyString(message.previous_request_id) &&
    nullableNonEmptyString(message.previous_response_id) &&
    Number.isSafeInteger(message.revision_index) && message.revision_index > 0 &&
    ACTIVE_REQUEST_PHASES.has(message.previous_phase) &&
    nonEmptyString(message.utterance_id);
}

function validResponseSuperseded(message) {
  return nonEmptyString(message.request_id) &&
    nullableNonEmptyString(message.response_id) &&
    nonEmptyString(message.superseding_request_id) &&
    ACTIVE_REQUEST_PHASES.has(message.previous_phase);
}
