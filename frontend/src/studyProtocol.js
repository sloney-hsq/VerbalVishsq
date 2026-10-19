const CONTROL_FIELDS = new Map([
  ['trial.start', new Set()],
  ['trial.task_presented', new Set()],
  ['answer.save', new Set(['draft_version', 'conclusion', 'evidence_refs', 'limitations'])],
  ['answer.submit', new Set(['submission_id', 'conclusion', 'evidence_refs', 'limitations'])],
  ['questionnaire.submit', new Set(['responses'])],
  ['control.stop', new Set()],
  ['view.rendered', new Set(['render_token', 'dashboard_revision', 'view_id', 'view_revision', 'render_generation', 'browser_duration_ms', 'presentation'])],
  ['view.render_failed', new Set(['render_token', 'dashboard_revision', 'view_id', 'view_revision', 'render_generation', 'browser_duration_ms', 'presentation', 'error_code'])],
]);
const FORBIDDEN_IDENTITY = new Set(['condition', 'participant_id', 'task_id', 'attempt_id', 'session_id', 'path']);

export function createStudyControlEvent(type, payload = {}, createId = defaultId, retryEvent = null) {
  if (retryEvent) {
    if (retryEvent.type !== type || !validEventId(retryEvent.client_event_id)) throw new Error('Invalid retry event');
    return structuredClone(retryEvent);
  }
  const allowed = CONTROL_FIELDS.get(type);
  if (!allowed || !payload || typeof payload !== 'object' || Array.isArray(payload)) throw new Error('Unsupported study control');
  for (const field of Object.keys(payload)) {
    if (!allowed.has(field) || FORBIDDEN_IDENTITY.has(field)) throw new Error(`Field is not allowed: ${field}`);
  }
  const clientEventId = createId();
  if (!validEventId(clientEventId)) throw new Error('Invalid client event id');
  return { type, client_event_id: clientEventId, ...structuredClone(payload) };
}

export function studyTaskVisible(state = {}) {
  return ['exploring', 'answering', 'completed'].includes(state.phase) && Boolean(state.task);
}

export function studyQuestionnaireVisible(state = {}) {
  return ['answering', 'completed'].includes(state.phase)
    && state.allowed_actions?.includes('questionnaire.submit') === true;
}

export function normalizeEvidenceRefs(value) {
  if (!Array.isArray(value)) return [];
  return value.flatMap(item => {
    if (!item || !Number.isSafeInteger(item.revision) || item.revision < 0
      || typeof item.artifact_id !== 'string'
      || !/^[A-Za-z0-9_.:-]{1,128}$/.test(item.artifact_id)
      || Object.keys(item).some(key => !['revision', 'artifact_id'].includes(key))) return [];
    return [{
      id:item.artifact_id,
      label:`Dashboard revision ${item.revision}`,
      ref:{revision:item.revision,artifact_id:item.artifact_id},
    }];
  });
}

export function selectedEvidenceRefs(options, selectedIds) {
  const selected = new Set(Array.isArray(selectedIds) ? selectedIds : []);
  return (Array.isArray(options) ? options : [])
    .filter(option => selected.has(option?.id))
    .map(option => structuredClone(option.ref));
}

export function dashboardSnapshotFromMessage(message = {}) {
  const state = message.state && typeof message.state === 'object' ? structuredClone(message.state) : {};
  return {
    viewList:Array.isArray(message.views) ? structuredClone(message.views) : Array.isArray(state.views) ? structuredClone(state.views) : [],
    state,
    revision:message.dashboard_revision,
    digest:message.dashboard_digest || null,
  };
}

export function createStudyProtocol() {
  const pending = new Map();
  const state = {
    answerSaved: false,
    connected: true,
    draft: { conclusion: '', evidence_refs: [], limitations: '' },
  };

  function queue(type, payload, createId, retryEvent = null) {
    const event = createStudyControlEvent(type, payload, createId, retryEvent);
    pending.set(event.client_event_id, structuredClone(event));
    if (type === 'answer.save') state.answerSaved = false;
    return event;
  }

  function applyReceipt(receipt) {
    if (receipt?.type !== 'study.receipt' || !['accepted', 'conflict', 'rejected'].includes(receipt.status)) return false;
    const event = pending.get(receipt.client_event_id);
    if (!event || event.type !== receipt.event_type) return false;
    if (event.type === 'answer.save' && receipt.status === 'accepted'
      && receipt.receipt?.draft_version !== event.draft_version) return false;
    pending.delete(receipt.client_event_id);
    if (event.type === 'answer.save') state.answerSaved = receipt.status === 'accepted';
    return true;
  }

  function updateDraft(update) {
    state.draft = {
      conclusion: String(update?.conclusion ?? state.draft.conclusion),
      evidence_refs: Array.isArray(update?.evidence_refs) ? [...update.evidence_refs] : [...state.draft.evidence_refs],
      limitations: String(update?.limitations ?? state.draft.limitations),
    };
    state.answerSaved = false;
  }

  function disconnect() {
    state.connected = false;
    return [];
  }

  return {
    queue, applyReceipt, updateDraft, disconnect,
    get answerSaved() { return state.answerSaved; },
    get draft() { return structuredClone(state.draft); },
  };
}

function validEventId(value) {
  return typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,128}$/.test(value);
}

function defaultId() {
  return globalThis.crypto?.randomUUID?.() || `evt-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
