import { ref } from "vue";
import { defineStore } from "pinia";

const MAX_TRANSCRIPT_ITEMS = 120;

export const useDashboardStore = defineStore("dashboard", () => {
  const views = ref([]);
  const datasetDescription = ref({});
  const dashboardRevision = ref(-1);
  const dashboardDigest = ref(null);
  const activeFilters = ref([]);
  const highlightedViewIds = ref([]);
  const highlightElement = ref(null);
  const highlightDimOthers = ref(true);

  // Flat chronological timeline: user, assistant, and tool items.
  const transcriptItems = ref([]);
  const currentUserItemId = ref(null);
  const currentAssistantResponseId = ref(null);
  const acceptedRevisionRequestIds = new Set();

  const isAssistantSpeaking = ref(false);
  const connectionStatus = ref("disconnected");
  const sessionReady = ref(false);
  const sessionMode = ref("fd_voice");
  const inputMode = ref("semantic_vad");
  const turnDetection = ref("semantic_vad");
  const provider = ref("qwen");
  const model = ref("qwen3.5-omni-plus-realtime");
  const inputAudioRate = ref(16000);
  const outputAudioRate = ref(24000);

  // ------------------------------------------------------------------
  // Dashboard state
  // ------------------------------------------------------------------

  function initViews(viewList = [], revision = null, state = {}) {
    activeFilters.value = [];
    highlightedViewIds.value = [];
    highlightElement.value = null;
    highlightDimOthers.value = true;
    transcriptItems.value = [];
    currentUserItemId.value = null;
    currentAssistantResponseId.value = null;
    acceptedRevisionRequestIds.clear();
    isAssistantSpeaking.value = false;
    dashboardRevision.value = -1;
    dashboardDigest.value = null;
    applyDashboardCommit({ viewList, revision, state });
  }

  function updateViews(viewList = [], revision = null) {
    return applyAuthoritativeViews(viewList, revision);
  }

  function applyDashboardCommit({
    viewList = [],
    state = {},
    revision = null,
    digest = null,
  } = {}) {
    const incomingRevision = resolvedRevision(
      viewList,
      revision ?? state.dashboard_revision,
    );
    if (!acceptDashboardRevision(incomingRevision, digest)) return false;

    if (Array.isArray(state.filters)) activeFilters.value = state.filters;
    const selected = Array.isArray(state.highlighted)
      ? uniqueIds(state.highlighted)
      : viewList
        .filter((view) => Boolean(view.highlighted))
        .map((view) => view.id);
    highlightedViewIds.value = selected;
    highlightElement.value = selected.length
      ? state.highlight_element ?? null
      : null;
    highlightDimOthers.value = state.dim_others ?? true;
    views.value = viewList.map((view) => ({ ...view }));
    return true;
  }

  function applyAuthoritativeViews(viewList, revision = null, digest = null) {
    const incomingRevision = resolvedRevision(viewList, revision);
    if (!acceptDashboardRevision(incomingRevision, digest)) return false;
    highlightedViewIds.value = viewList
      .filter((view) => Boolean(view.highlighted))
      .map((view) => view.id);
    if (!highlightedViewIds.value.length) {
      highlightElement.value = null;
    }
    views.value = viewList.map((view) => ({ ...view }));
    return true;
  }

  function acceptDashboardRevision(revision, digest = null) {
    if (revision === null || revision === undefined || revision === "") return true;
    const incomingRevision = Number(revision);
    if (!Number.isSafeInteger(incomingRevision) || incomingRevision < 0) return false;
    if (incomingRevision < dashboardRevision.value) return false;
    if (incomingRevision === dashboardRevision.value) {
      return typeof digest === "string" && digest === dashboardDigest.value;
    }
    dashboardRevision.value = incomingRevision;
    dashboardDigest.value = typeof digest === "string" ? digest : null;
    return true;
  }

  function setSessionInfo(info = {}) {
    if (info.mode) sessionMode.value = info.mode;
    if (info.inputMode) inputMode.value = info.inputMode;
    if (info.turnDetection) turnDetection.value = info.turnDetection;
    if (info.provider) provider.value = info.provider;
    if (info.model) model.value = info.model;
    if (info.inputAudioRate) inputAudioRate.value = info.inputAudioRate;
    if (info.outputAudioRate) outputAudioRate.value = info.outputAudioRate;
  }

  function highlightViews(ids, element = null, dimOthers = true) {
    const normalized = uniqueIds(ids);
    highlightedViewIds.value = normalized;
    highlightElement.value = element;
    highlightDimOthers.value = Boolean(dimOthers);
    const selected = new Set(normalized);
    views.value.forEach((view) => {
      view.highlighted = selected.has(view.id);
    });
  }

  function clearHighlight() {
    highlightedViewIds.value = [];
    highlightElement.value = null;
    highlightDimOthers.value = true;
    views.value.forEach((view) => {
      view.highlighted = false;
    });
  }

  function handleToolResult(message = {}) {
    // Tool-result messages describe one action in the transcript. Dashboard
    // state itself changes only when the backend publishes the completed
    // batch's dashboard_commit snapshot.
    completeToolItem(message.call_id, message);
  }

  // ------------------------------------------------------------------
  // Flat transcript timeline
  // ------------------------------------------------------------------

  function beginUserTranscript({ utteranceId = null, requestId = null, text = "" } = {}) {
    const existing = findPendingUser(utteranceId);
    if (existing) {
      if (requestId) existing.requestId = requestId;
      if (requestId && acceptedRevisionRequestIds.has(requestId)) {
        existing.revisionAccepted = true;
        acceptedRevisionRequestIds.delete(requestId);
      }
      return existing;
    }

    const item = makeItem({
      role: "user",
      text,
      status: "listening",
      utteranceId: utteranceId || makeId("utterance"),
      requestId,
    });
    item.revisionAccepted = takePendingRevision(requestId);
    transcriptItems.value.push(item);
    currentUserItemId.value = item.id;
    trimTimeline();
    return item;
  }

  function updateUserTranscript({ utteranceId = null, requestId = null, text = "", status = "listening" } = {}) {
    const item = findPendingUser(utteranceId) || beginUserTranscript({ utteranceId, requestId, text });
    item.text = String(text || "");
    item.status = status;
    if (requestId) item.requestId = requestId;
    if (requestId && acceptedRevisionRequestIds.has(requestId)) {
      item.revisionAccepted = true;
      acceptedRevisionRequestIds.delete(requestId);
    }
    return item;
  }

  function completeUserTranscript(text, { utteranceId = null, requestId = null } = {}) {
    const clean = String(text || "").trim();
    if (!clean) return null;

    const item = findPendingUser(utteranceId);
    if (item) {
      item.text = clean;
      item.status = "completed";
      if (requestId) item.requestId = requestId;
      if (requestId && acceptedRevisionRequestIds.has(requestId)) {
        item.revisionAccepted = true;
        acceptedRevisionRequestIds.delete(requestId);
      }
      item.completedAt = Date.now();
      currentUserItemId.value = null;
      return item;
    }

    const completed = makeItem({
      role: "user",
      text: clean,
      status: "completed",
      utteranceId: utteranceId || makeId("utterance"),
      requestId,
    });
    completed.revisionAccepted = takePendingRevision(requestId);
    completed.completedAt = completed.startedAt;
    transcriptItems.value.push(completed);
    trimTimeline();
    return completed;
  }

  function beginAssistantResponse(responseId, requestId = null) {
    if (responseId) currentAssistantResponseId.value = responseId;
    const item = findAssistant(responseId);
    if (item && requestId) item.requestId = requestId;
  }

  function appendAssistantTranscript(responseId, delta = "", requestId = null) {
    const id = responseId || currentAssistantResponseId.value || makeId("response");
    currentAssistantResponseId.value = id;
    let item = findAssistant(id);
    if (!item) {
      item = makeItem({
        role: "assistant",
        responseId: id,
        requestId,
        status: "streaming",
      });
      transcriptItems.value.push(item);
      trimTimeline();
    }
    item.text += String(delta || "");
    item.status = "streaming";
    if (requestId) item.requestId = requestId;
    return item;
  }

  function acceptRevision(requestId) {
    if (!requestId) return false;
    const user = transcriptItems.value.find((item) => item.role === "user" && item.requestId === requestId);
    if (!user) {
      acceptedRevisionRequestIds.add(requestId);
      while (acceptedRevisionRequestIds.size > 256) {
        acceptedRevisionRequestIds.delete(acceptedRevisionRequestIds.values().next().value);
      }
      return true;
    }
    user.revisionAccepted = true;
    return true;
  }

  function takePendingRevision(requestId) {
    if (!requestId || !acceptedRevisionRequestIds.has(requestId)) return false;
    acceptedRevisionRequestIds.delete(requestId);
    return true;
  }

  function markRequestSuperseded(requestId, responseId = null) {
    if (!requestId && !responseId) return false;
    let changed = false;
    transcriptItems.value.forEach((item) => {
      if ((requestId && item.requestId === requestId) || (responseId && item.responseId === responseId)) {
        item.superseded = true;
        changed = true;
      }
    });
    return changed;
  }

  function finishSupersededBatch(batchId) {
    return finishTerminalBatch(batchId, "superseded");
  }

  function finishTerminalBatch(batchId, commitStatus) {
    if (!batchId) return false;
    let changed = false;
    transcriptItems.value.forEach((item) => {
      if (item.role === "tool" && item.batchId === batchId && item.status === "running") {
        item.status = commitStatus === "superseded" ? "superseded" :
          commitStatus === "failed" || commitStatus === "conflicted" ? "error" : "completed";
        item.commitStatus = commitStatus;
        item.stateChanged = commitStatus === "committed";
        if (item.status === "error") item.error = "Tool batch did not update the dashboard";
        item.completedAt = Date.now();
        changed = true;
      }
    });
    return changed;
  }

  function completeAssistantResponse(responseId) {
    const item = findAssistant(responseId);
    if (item) {
      if (!item.text.trim()) removeItem(item.id);
      else if (item.status !== "interrupted") {
        item.status = "completed";
        item.completedAt = Date.now();
      }
    }
    if (!responseId || currentAssistantResponseId.value === responseId) {
      currentAssistantResponseId.value = null;
    }
  }

  function interruptAssistantResponse(responseId) {
    const id = responseId || currentAssistantResponseId.value;
    const item = findAssistant(id);
    if (item) {
      if (!item.text.trim()) removeItem(item.id);
      else {
        item.status = "interrupted";
        item.completedAt = Date.now();
      }
    }
    if (!id || currentAssistantResponseId.value === id) {
      currentAssistantResponseId.value = null;
    }
  }

  function addToolItem({
    name,
    arguments: rawArguments,
    summary,
    callId,
    batchId = null,
    cardKey = null,
    responseId,
    requestId = null,
  } = {}) {
    const parameters = parseArguments(rawArguments);
    const item = makeItem({
      role: "tool",
      status: "running",
      callId: callId || makeId("call"),
      batchId,
      cardKey: cardKey || toolCardKey(batchId, callId),
      responseId: responseId || null,
      requestId,
      toolName: name || "tool",
      parameters,
      summary: summary || summarizeTool(name, parameters),
    });
    transcriptItems.value.push(item);
    trimTimeline();
    return item;
  }

  function completeToolItem(callId, result = {}) {
    if (!callId) return;
    const batchId = result.correlation?.batch_id || result.batch_id || null;
    const cardKey = result.cardKey || toolCardKey(batchId, callId);
    const item = transcriptItems.value.find(
      (entry) => entry.role === "tool" && (
        cardKey ? entry.cardKey === cardKey : entry.callId === callId
      ),
    );
    if (!item) return;
    const failed = result.execution_status === "failed" || result.success === false;
    item.status = failed ? "error" : "completed";
    item.executionStatus = result.execution_status || null;
    item.commitStatus = result.commit_status || null;
    item.stateChanged = result.state_changed === true;
    item.error = failed
      ? String(result.error?.message || result.error || result.summary || "Tool execution failed")
      : null;
    if (result.summary) item.summary = String(result.summary);
    if (item.error) item.expanded = true;
    item.completedAt = Date.now();
  }

  function failRunningToolItems(responseId, error) {
    const message = String(error || "Tool batch could not finish");
    transcriptItems.value.forEach((item) => {
      if (item.role !== "tool" || item.status !== "running") return;
      if (responseId && item.responseId && item.responseId !== responseId) return;
      item.status = "error";
      item.error = message;
      item.expanded = true;
      item.completedAt = Date.now();
    });
  }

  function toggleToolDetails(itemId) {
    const item = transcriptItems.value.find((entry) => entry.id === itemId);
    if (item?.role === "tool") item.expanded = !item.expanded;
  }

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  function findPendingUser(utteranceId) {
    if (utteranceId) {
      const exact = transcriptItems.value.find(
        (item) => item.role === "user" && item.utteranceId === utteranceId && item.status !== "completed",
      );
      if (exact) return exact;
    }
    if (!currentUserItemId.value) return null;
    return transcriptItems.value.find((item) => item.id === currentUserItemId.value) || null;
  }

  function findAssistant(responseId) {
    if (!responseId) return null;
    return transcriptItems.value.find(
      (item) => item.role === "assistant" && item.responseId === responseId,
    ) || null;
  }

  function makeItem({
    role,
    text = "",
    status = "completed",
    responseId = null,
    utteranceId = null,
    callId = null,
    batchId = null,
    cardKey = null,
    toolName = null,
    parameters = null,
    summary = null,
    error = null,
    requestId = null,
  }) {
    const startedAt = Date.now();
    return {
      id: makeId(role),
      role,
      text,
      status,
      responseId,
      requestId,
      revisionAccepted: false,
      superseded: false,
      utteranceId,
      callId,
      batchId,
      cardKey,
      toolName,
      parameters,
      summary,
      error,
      expanded: false,
      startedAt,
      completedAt: status === "completed" ? startedAt : null,
    };
  }

  function parseArguments(value) {
    if (!value) return {};
    if (typeof value === "object") return value;
    try {
      return JSON.parse(value);
    } catch (_) {
      return { value: String(value) };
    }
  }

  function summarizeTool(name, parameters = {}) {
    const label = String(name || "tool").replace(/_/g, " ");
    const first = Object.entries(parameters)
      .filter(([, value]) => value !== null && value !== undefined && value !== "")
      .slice(0, 2)
      .map(([key, value]) => `${key}=${compactValue(value)}`);
    return first.length ? `${label} · ${first.join(" · ")}` : label;
  }

  function compactValue(value) {
    if (Array.isArray(value)) return value.slice(0, 4).join(",");
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function uniqueIds(value) {
    const source = Array.isArray(value) ? value : [value];
    return [...new Set(source.filter(Boolean))];
  }

  function removeItem(itemId) {
    const index = transcriptItems.value.findIndex((item) => item.id === itemId);
    if (index >= 0) transcriptItems.value.splice(index, 1);
  }

  function trimTimeline() {
    if (transcriptItems.value.length > MAX_TRANSCRIPT_ITEMS) {
      transcriptItems.value = transcriptItems.value.slice(-MAX_TRANSCRIPT_ITEMS);
    }
  }

  function makeId(prefix) {
    return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function toolCardKey(batchId, callId) {
    return batchId && callId ? `${batchId}:${callId}` : null;
  }

  return {
    views,
    datasetDescription,
    dashboardRevision,
    dashboardDigest,
    activeFilters,
    highlightedViewIds,
    highlightElement,
    highlightDimOthers,
    transcriptItems,
    isAssistantSpeaking,
    connectionStatus,
    sessionReady,
    sessionMode,
    inputMode,
    turnDetection,
    provider,
    model,
    inputAudioRate,
    outputAudioRate,
    initViews,
    updateViews,
    applyDashboardCommit,
    acceptDashboardRevision,
    setSessionInfo,
    highlightViews,
    clearHighlight,
    handleToolResult,
    beginUserTranscript,
    updateUserTranscript,
    completeUserTranscript,
    beginAssistantResponse,
    appendAssistantTranscript,
    acceptRevision,
    markRequestSuperseded,
    finishSupersededBatch,
    finishTerminalBatch,
    completeAssistantResponse,
    interruptAssistantResponse,
    addToolItem,
    completeToolItem,
    failRunningToolItems,
    toggleToolDetails,
  };
});

function resolvedRevision(viewList, explicitRevision) {
  if (explicitRevision !== null && explicitRevision !== undefined) {
    return explicitRevision;
  }
  const revisions = (Array.isArray(viewList) ? viewList : [])
    .map((view) => Number(view?.revision))
    .filter(Number.isFinite);
  return revisions.length ? Math.max(...revisions) : null;
}
