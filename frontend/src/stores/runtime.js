import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { validInputPolicy } from "../realtimePolicy.js";

export const useRuntimeStore = defineStore("runtime", () => {
  const phase = ref("connecting");
  // This server-owned input floor is independent of presentation/playback phase.
  const inputPolicySeq = ref(-1);
  const condition = ref(null);
  const inputPhase = ref("connecting");
  const acceptsAudio = ref(false);
  const toolRunning = ref(false);
  const activeToolBatchId = ref(null);
  const activeTools = ref([]);
  const configurationError = ref("");
  const dashboardState = ref({
    filters: [],
    highlighted: [],
    views: [],
  });
  const filteredRows = ref(null);
  const lastToolSummary = ref("");
  const lastToolError = ref("");
  const lastToolDurationMs = ref(null);
  const ignoredAudioChunks = ref(0);
  const studyState = ref(null);
  const studyReceipt = ref(null);
  const answerSaved = ref(false);
  const renderEnvelope = ref(null);

  const phaseLabel = computed(() => {
    switch (phase.value) {
      case "ready":
        return "Ready";
      case "listening":
        return "Listening";
      case "processing":
        return "Understanding request";
      case "assistant_speaking":
        return "Assistant speaking";
      case "reading_dashboard":
        return "Reading dashboard";
      case "updating_dashboard":
        return "Updating dashboard";
      case "configuration_error":
        return "Qwen configuration required";
      case "error":
        return "Runtime error";
      case "disconnected":
        return "Disconnected";
      default:
        return "Connecting";
    }
  });

  const phaseDetail = computed(() => {
    if (configurationError.value) return configurationError.value;
    if (toolRunning.value && activeTools.value.length) {
      return activeTools.value.map((tool) => tool.label || tool.name).join(" · ");
    }
    if (phase.value === "ready" && lastToolSummary.value) {
      return lastToolSummary.value;
    }
    return "";
  });

  const activeFilterCount = computed(() => (
    Array.isArray(dashboardState.value?.filters)
      ? dashboardState.value.filters.length
      : 0
  ));

  const viewCount = computed(() => (
    Array.isArray(dashboardState.value?.views)
      ? dashboardState.value.views.length
      : 0
  ));

  function applyInputPolicy(message) {
    if (!validInputPolicy(message, inputPolicySeq.value)) return false;
    inputPolicySeq.value = message.seq;
    condition.value = message.condition;
    inputPhase.value = message.phase;
    acceptsAudio.value = message.accepts_audio;
    return true;
  }

  function setPhase(nextPhase, options = {}) {
    phase.value = nextPhase || "ready";
    if (Array.isArray(options.tools)) {
      activeTools.value = options.tools;
    } else if (["ready", "listening", "assistant_speaking", "disconnected", "error", "configuration_error"].includes(phase.value)) {
      activeTools.value = [];
    }
    if (typeof options.toolRunning === "boolean") {
      toolRunning.value = options.toolRunning;
      if (!toolRunning.value) activeToolBatchId.value = null;
    }
  }

  function setConfigurationError(message = "") {
    configurationError.value = String(message || "").trim();
    if (configurationError.value) {
      phase.value = "configuration_error";
      toolRunning.value = false;
      activeTools.value = [];
    }
  }

  function startToolBatch(message = {}) {
    toolRunning.value = true;
    activeToolBatchId.value = message.correlation?.batch_id || message.batch_id || null;
    activeTools.value = Array.isArray(message.tools) ? message.tools : [];
    phase.value = message.changes_dashboard ? "updating_dashboard" : "reading_dashboard";
    lastToolError.value = "";
    ignoredAudioChunks.value = 0;
  }

  function finishToolBatch(message = {}) {
    const batchId = message.correlation?.batch_id || message.batch_id || null;
    if (!batchId || batchId !== activeToolBatchId.value) return false;
    toolRunning.value = false;
    activeToolBatchId.value = null;
    activeTools.value = [];
    phase.value = message.followup_requested === false ? "ready" : "processing";
    if (message.fatal_error) {
      lastToolError.value = String(message.fatal_error);
      lastToolSummary.value = "";
    }
    lastToolDurationMs.value = Number.isFinite(Number(message.duration_ms))
      ? Number(message.duration_ms)
      : null;
    ignoredAudioChunks.value = Number(message.ignored_audio_chunks || 0);
    return true;
  }

  function recordToolResult(message = {}) {
    if (message.summary) lastToolSummary.value = String(message.summary);
    if (message.execution_status === "failed" || message.success === false) {
      lastToolError.value = String(message.error?.message || message.error || message.summary || "Tool execution failed");
    } else {
      lastToolError.value = "";
    }
  }

  function updateDashboardState(state = {}) {
    dashboardState.value = {
      filters: Array.isArray(state.filters) ? state.filters : [],
      highlighted: Array.isArray(state.highlighted) ? state.highlighted : [],
      views: Array.isArray(state.views) ? state.views : [],
      ...state,
    };
    if (
      state.filtered_rows !== undefined &&
      state.filtered_rows !== null &&
      Number.isFinite(Number(state.filtered_rows))
    ) {
      filteredRows.value = Number(state.filtered_rows);
    }
  }

  function applyStudyState(message = {}) {
    const phases = new Set(['preparing', 'ready', 'exploring', 'answering', 'completed', 'aborted']);
    if (message.type !== 'trial.state' || !phases.has(message.phase)) return false;
    const taskVisible = ['exploring', 'answering', 'completed'].includes(message.phase);
    studyState.value = {
      phase: message.phase,
      freeze_status: message.freeze_status || null,
      remaining_ms: Number.isFinite(Number(message.remaining_ms)) ? Math.max(0, Number(message.remaining_ms)) : null,
      task: taskVisible && message.task && typeof message.task === 'object' ? structuredClone(message.task) : null,
      answer_status: message.answer_status || null,
      evidence_refs_ready: Array.isArray(message.evidence_refs_ready)
        ? structuredClone(message.evidence_refs_ready)
        : Boolean(message.evidence_refs_ready),
      allowed_actions: Array.isArray(message.allowed_actions) ? [...message.allowed_actions] : [],
      error_code: message.error_code || null,
    };
    return true;
  }

  function noteStudyControl(event = {}) {
    if (event.type === 'answer.save') answerSaved.value = false;
  }

  function applyStudyReceipt(receipt = {}) {
    studyReceipt.value = structuredClone(receipt);
    if (receipt.status === 'accepted' && receipt.event_type === 'answer.save') answerSaved.value = true;
  }

  function setRenderEnvelope(envelope) {
    renderEnvelope.value = envelope && typeof envelope === 'object' ? structuredClone(envelope) : null;
  }

  function resetRuntime() {
    inputPolicySeq.value = -1;
    condition.value = null;
    inputPhase.value = "connecting";
    acceptsAudio.value = false;
    phase.value = "connecting";
    toolRunning.value = false;
    activeToolBatchId.value = null;
    activeTools.value = [];
    configurationError.value = "";
    dashboardState.value = {
      filters: [],
      highlighted: [],
      views: [],
    };
    filteredRows.value = null;
    lastToolSummary.value = "";
    lastToolError.value = "";
    lastToolDurationMs.value = null;
    ignoredAudioChunks.value = 0;
    studyState.value = null;
    studyReceipt.value = null;
    answerSaved.value = false;
    renderEnvelope.value = null;
  }

  return {
    inputPolicySeq,
    condition,
    inputPhase,
    acceptsAudio,
    applyInputPolicy,
    phase,
    toolRunning,
    activeToolBatchId,
    activeTools,
    configurationError,
    dashboardState,
    filteredRows,
    lastToolSummary,
    lastToolError,
    lastToolDurationMs,
    ignoredAudioChunks,
    studyState,
    studyReceipt,
    answerSaved,
    renderEnvelope,
    phaseLabel,
    phaseDetail,
    activeFilterCount,
    viewCount,
    setPhase,
    setConfigurationError,
    startToolBatch,
    finishToolBatch,
    recordToolResult,
    updateDashboardState,
    applyStudyState,
    noteStudyControl,
    applyStudyReceipt,
    setRenderEnvelope,
    resetRuntime,
  };
});
