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
    resetRuntime,
  };
});
