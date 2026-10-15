const PROTOCOL = "verbalvis.rrt";
const VERSION = 1;
const COMMIT_STATUSES = new Set([
  "committed",
  "read_only",
  "revoked",
  "failed",
  "conflicted",
]);
const CONDITIONS = new Set(["turn_taking", "revision_enabled"]);
const EVENTS = new Set(["dashboard_commit"]);

export function isVersionedRrtMessage(candidate) {
  return isRecord(candidate) && candidate.protocol === PROTOCOL;
}

export function validateRrtEnvelope(candidate) {
  if (!isRecord(candidate)) return reject("invalid_envelope");
  if (candidate.protocol !== PROTOCOL) return reject("invalid_protocol");
  if (candidate.version !== VERSION) return reject("invalid_version");
  if (!isPositiveInteger(candidate.seq)) return reject("invalid_seq");
  if (!EVENTS.has(candidate.event)) {
    return reject("invalid_event");
  }
  if (!COMMIT_STATUSES.has(candidate.commit_status)) {
    return reject("invalid_commit_status");
  }

  const correlationError = validateCorrelation(candidate.correlation);
  if (correlationError) return reject(correlationError);

  const payloadError = validatePayload(candidate);
  if (payloadError) return reject(payloadError);

  return { ok: true, value: candidate };
}

function validateCorrelation(correlation) {
  if (!isRecord(correlation)) return "invalid_correlation";
  const strings = ["session_id", "trial_id", "condition", "response_id"];
  for (const field of strings) {
    if (typeof correlation[field] !== "string" || !correlation[field].trim()) {
      return `invalid_correlation.${field}`;
    }
  }
  if (!CONDITIONS.has(correlation.condition)) return "invalid_correlation.condition";
  for (const field of ["intent_epoch", "base_revision"]) {
    if (!isNonNegativeInteger(correlation[field])) {
      return `invalid_correlation.${field}`;
    }
  }
  for (const field of ["batch_id", "call_id"]) {
    if (!(correlation[field] === null || typeof correlation[field] === "string")) {
      return `invalid_correlation.${field}`;
    }
  }
  return null;
}

function validatePayload(envelope) {
  const { payload } = envelope;
  if (!isRecord(payload)) return "invalid_payload";
  if (envelope.event !== "dashboard_commit") return null;
  if (!isNonNegativeInteger(payload.revision)) return "invalid_payload.revision";
  if (!isPlainObject(payload.snapshot)) return "invalid_payload.snapshot";
  if (!Array.isArray(payload.snapshot.views)) return "invalid_payload.snapshot.views";
  for (const field of ["filters", "highlighted"]) {
    if (payload.snapshot[field] !== undefined && !Array.isArray(payload.snapshot[field])) {
      return `invalid_payload.snapshot.${field}`;
    }
  }
  if (typeof payload.snapshot_digest !== "string" || !payload.snapshot_digest) {
    return "invalid_payload.snapshot_digest";
  }
  return null;
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isPlainObject(value) {
  if (!isRecord(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function isPositiveInteger(value) {
  return Number.isSafeInteger(value) && value > 0;
}

function isNonNegativeInteger(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

function reject(reason) {
  return { ok: false, reason };
}
