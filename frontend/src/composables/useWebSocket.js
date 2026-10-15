import { nextTick, onBeforeUnmount, ref } from "vue";
import { storeToRefs } from "pinia";
import { useDashboardStore } from "../stores/dashboard";
import { useRuntimeStore } from "../stores/runtime";
import {
  captureBlockedForPlaybackStop,
  canTransmitAudio,
  withExperimentContext,
} from "../realtimePolicy";
import { legacyToolItemPayload, projectLegacyEvents } from "../rrtLegacyProjection";
import {
  isVersionedRrtMessage,
  validateRrtEnvelope,
} from "../protocol/rrtContract";
import {
  createRrtProjectionState,
  projectRrtEvent,
} from "../protocol/rrtProjector";
import { applyRrtEffects } from "../protocol/rrtEffects";
import { SessionProjection } from '../sessionProjection.js';

export { legacyToolItemPayload, projectLegacyEvents } from "../rrtLegacyProjection";

/**
 * Browser-side FD-Voice protocol adapter.
 *
 * One page lifecycle owns one backend WebSocket and one Qwen Realtime session.
 * Start/Stop mic only controls PCM capture; it never creates another session.
 */
export function useWebSocket(audioPlayer) {
  const dashboard = useDashboardStore();
  const runtime = useRuntimeStore();
  const { toolRunning } = storeToRefs(runtime);
  const socket = ref(null);

  let activeResponseId = null;
  let analysisId = createAnalysisId();
  let rrtProjectionState = createRrtProjectionState();
  let sessionProjection = new SessionProjection();

  audioPlayer?.setPlaybackIdleHandler?.((event = {}) => {
    dashboard.isAssistantSpeaking = false;
    if (!toolRunning.value && !runtime.configurationError) runtime.setPhase("ready");
    sendPlaybackStopped(
      event.responseId || event.response_id || null,
      event.reason || "natural_end",
      event.playbackCursor || event.playback_cursor || null,
    );
  });

  function connect() {
    if (
      socket.value &&
      [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.value.readyState)
    ) return;

    runtime.resetRuntime();
    rrtProjectionState = createRrtProjectionState();
    sessionProjection = new SessionProjection();
    runtime.setPhase("connecting");
    dashboard.connectionStatus = "connecting";
    dashboard.sessionReady = false;
    audioPlayer?.setCaptureBlocked?.(true);

    const ws = new WebSocket(buildWebSocketUrl());
    socket.value = ws;

    ws.onopen = () => {
      if (socket.value !== ws) return;
      dashboard.connectionStatus = "connected";
      runtime.setPhase("connecting");
    };

    ws.onclose = () => {
      if (socket.value !== ws) return;
      audioPlayer?.setCaptureBlocked?.(true);
      audioPlayer?.stopAssistantAudio?.({
        blockNewAudio: true,
        reason: "socket_closed",
      });
      activeResponseId = null;
      dashboard.isAssistantSpeaking = false;
      dashboard.sessionReady = false;
      if (runtime.configurationError) {
        dashboard.connectionStatus = "configuration_error";
        runtime.setPhase("configuration_error", { toolRunning: false, tools: [] });
      } else {
        dashboard.connectionStatus = "disconnected";
        runtime.setPhase("disconnected", { toolRunning: false, tools: [] });
      }
      socket.value = null;
    };

    ws.onerror = () => {
      if (socket.value !== ws) return;
      stopAssistantPlayback(activeResponseId, "socket_error", false);
      dashboard.connectionStatus = "disconnected";
      dashboard.sessionReady = false;
      runtime.setPhase("error", { toolRunning: false, tools: [] });
    };

    ws.onmessage = (event) => {
      if (socket.value !== ws) return;
      try {
        dispatch(JSON.parse(event.data));
      } catch (error) {
        console.error("Invalid realtime message", error);
      }
    };
  }

  function dispatch(message = {}) {
    if (!sessionProjection.accept(message)) return;
    if (isVersionedRrtMessage(message)) {
      const validation = validateRrtEnvelope(message);
      if (!validation.ok) {
        console.warn("Rejected malformed RRT envelope", validation.reason);
        return;
      }
      const projected = projectRrtEvent(rrtProjectionState, validation.value);
      rrtProjectionState = projected.state;
      if (!projected.accepted || !projected.effects.length) return;
      void applyRrtEffects(projected.effects, {
        dashboard,
        runtime,
        nextTick,
        sendAck: sendRrtAck,
      }).catch((error) => console.error("RRT projection failed", error));
      return;
    }
    projectLegacyEvents(message, dispatchLegacyEvent);
  }

  function dispatchLegacyEvent(message = {}) {
    switch (message.type) {
      case "input_policy":
        runtime.applyInputPolicy(message);
        break;
      case "init":
        activeResponseId = null;
        dashboard.datasetDescription = message.dataset || {};
        dashboard.initViews(
          message.views || [],
          message.dashboard_revision,
          message.state || {},
        );
        syncSessionInfo(message);
        runtime.updateDashboardState(
          message.state || { views: message.views || [] },
        );
        break;

      case "configuration_error":
        activeResponseId = null;
        audioPlayer?.setCaptureBlocked?.(true);
        audioPlayer?.stopAssistantAudio?.({
          blockNewAudio: true,
          reason: "configuration_error",
        });
        dashboard.sessionReady = false;
        dashboard.connectionStatus = "configuration_error";
        runtime.setConfigurationError(message.message || "Qwen configuration required.");
        console.error("Qwen configuration error", message.message);
        break;

      case "session_updated":
        syncSessionInfo(message);
        analysisId = normalizeAnalysisId(message.analysis_id) || analysisId;
        window.__verbalvis_analysis_id = analysisId;
        break;

      case "session_ready":
        runtime.setConfigurationError("");
        audioPlayer?.setCaptureBlocked?.(false);
        dashboard.connectionStatus = "connected";
        dashboard.sessionReady = true;
        runtime.setPhase("ready");
        break;

      case "assistant_response_started":
        if (!message.response_id) break;
        audioPlayer?.setCaptureBlocked?.(false);
        activeResponseId = message.response_id;
        dashboard.beginAssistantResponse(activeResponseId, message.request_id);
        audioPlayer?.beginAssistantResponse?.(activeResponseId);
        runtime.setPhase("processing");
        break;

      case "audio":
        if (!message.response_id || message.response_id !== activeResponseId) break;
        if (audioPlayer?.enqueue?.(message.data, message) !== false) {
          dashboard.isAssistantSpeaking = true;
          runtime.setPhase("assistant_speaking");
        }
        break;

      case "transcript":
        handleTranscript(message);
        break;

      case "revision_received":
        dashboard.acceptRevision(message.request_id);
        break;

      case "response_superseded":
        dashboard.markRequestSuperseded(message.request_id, message.response_id);
        break;

      case "response_done":
        if (!message.response_id || message.response_id !== activeResponseId) break;
        dashboard.completeAssistantResponse(message.response_id);
        audioPlayer?.flush?.(message);
        activeResponseId = null;
        if (!toolRunning.value && !dashboard.isAssistantSpeaking) {
          runtime.setPhase("ready");
        }
        break;

      case "speech_started":
        runtime.setPhase("listening");
        dashboard.beginUserTranscript({
          utteranceId: message.utterance_id,
          text: message.text || "",
        });
        break;

      case "speech_stopped":
        if (!toolRunning.value) runtime.setPhase("processing");
        break;

      case "assistant_playback_stop":
        stopAssistantPlayback(
          message.response_id,
          message.reason || "user_interruption",
          true,
        );
        break;

      case "tool_execution_started":
        runtime.startToolBatch(message);
        break;

      case "tool_execution_finished":
        dashboard.finishTerminalBatch(message.batch_id || message.correlation?.batch_id,
          message.commit_status || message.status);
        if (message.fatal_error) {
          dashboard.failRunningToolItems(
            message.response_id,
            message.fatal_error,
          );
        }
        runtime.finishToolBatch(message);
        break;

      case "tool_call":
        dashboard.addToolItem(legacyToolItemPayload(message));
        break;

      case "tool_result":
        dashboard.handleToolResult(message);
        runtime.recordToolResult(message);
        break;

      case "dashboard_commit":
        if (dashboard.applyDashboardCommit({
          viewList: message.views || [],
          state: message.state || {},
          revision: message.dashboard_revision,
        })) {
          runtime.updateDashboardState(message.state || {});
          void nextTick().then(() => sendRrtAck({type:'dashboard_projection_ack', batch_id:message.batch_id,
            response_id:message.response_id, dashboard_revision:message.dashboard_revision}));
        }
        break;

      case "runtime_state":
        if (message.phase === "configuration_error") {
          runtime.setPhase("configuration_error", {
            toolRunning: false,
            tools: [],
          });
        } else {
          runtime.setPhase(message.phase || "ready", {
            toolRunning: Boolean(message.tool_running),
            tools: message.tools || [],
          });
        }
        break;

      case "error":
        audioPlayer?.setCaptureBlocked?.(true);
        stopAssistantPlayback(activeResponseId, "realtime_error", false);
        runtime.setPhase("error", { toolRunning: false, tools: [] });
        runtime.recordToolResult({
          success: false,
          error: message.message || "Realtime server error",
        });
        console.error("Realtime server error", message.message);
        break;
    }
  }

  function handleTranscript(message) {
    if (message.role === "assistant") {
      if (!message.response_id || message.response_id !== activeResponseId) return;
      dashboard.appendAssistantTranscript(
        message.response_id,
        message.delta || message.text || "",
        message.request_id || null,
      );
      return;
    }
    if (message.role !== "user") return;

    const utteranceId = message.utterance_id || message.item_id || null;
    const hasDelta = typeof message.delta === "string";
    const text = hasDelta ? message.delta : message.text;
    const partial = (
      message.status === "partial" ||
      message.completed === false ||
      message.is_final === false ||
      hasDelta
    );
    if (partial) {
      dashboard.updateUserTranscript({ utteranceId, text, status: "listening", requestId: message.request_id || null });
    } else {
      dashboard.completeUserTranscript(text, { utteranceId, requestId: message.request_id || null });
    }
  }

  function stopAssistantPlayback(responseId, reason, acknowledge) {
    const stoppedId = responseId || activeResponseId;
    dashboard.isAssistantSpeaking = false;
    dashboard.interruptAssistantResponse(stoppedId);

    const playbackCursor = audioPlayer?.stopAssistantAudio?.({
      responseId: stoppedId,
      blockNewAudio: captureBlockedForPlaybackStop(reason),
      reason,
    }) || null;

    if (!responseId || responseId === activeResponseId) activeResponseId = null;
    if (acknowledge) sendPlaybackStopped(stoppedId, reason, playbackCursor);
  }

  function syncSessionInfo(message = {}) {
    dashboard.setSessionInfo({
      mode: message.mode,
      inputMode: message.input_mode,
      turnDetection: message.turn_detection,
      provider: message.provider,
      model: message.model,
      inputAudioRate: message.input_audio_rate,
      outputAudioRate: message.output_audio_rate,
    });
  }

  function sendAudio(base64Pcm) {
    if (!canTransmitAudio({
      sessionReady: dashboard.sessionReady,
      acceptsAudio: runtime.acceptsAudio,
      captureBlocked: audioPlayer?.captureBlocked?.value,
      socketOpen: Boolean(socket.value && socket.value.readyState === WebSocket.OPEN),
    })) return false;
    socket.value.send(JSON.stringify({ type: "audio", data: base64Pcm }));
    return true;
  }

  function sendPlaybackStopped(responseId, reason, playbackCursor) {
    if (!socket.value || socket.value.readyState !== WebSocket.OPEN) return;
    socket.value.send(JSON.stringify({
      type: "playback_stopped",
      response_id: responseId,
      reason,
      playback_cursor: playbackCursor || null,
    }));
  }

  function sendRrtAck(acknowledgement) {
    if (!socket.value || socket.value.readyState !== WebSocket.OPEN) return false;
    socket.value.send(JSON.stringify(acknowledgement));
    return true;
  }

  function disconnect() {
    audioPlayer?.setCaptureBlocked?.(true);
    audioPlayer?.stopAssistantAudio?.({
      blockNewAudio: true,
      reason: "disconnect",
    });
    activeResponseId = null;
    dashboard.sessionReady = false;
    socket.value?.close();
    socket.value = null;
    runtime.setPhase("disconnected", { toolRunning: false, tools: [] });
  }

  function buildWebSocketUrl() {
    const params = new URLSearchParams(window.location.search);
    const explicit = params.get("ws") || import.meta.env.VITE_REALTIME_WS_URL;
    if (explicit) {
      const url = new URL(explicit, window.location.href);
      if (url.protocol === "http:") url.protocol = "ws:";
      if (url.protocol === "https:") url.protocol = "wss:";
      url.searchParams.set("analysis_id", analysisId);
      return withExperimentContext(url.toString(), window.location.search);
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const pathValue = params.get("wsPath") || import.meta.env.VITE_REALTIME_WS_PATH || "/ws";
    const path = pathValue.startsWith("/") ? pathValue : `/${pathValue}`;
    const url = new URL(`${protocol}//${window.location.host}${path}`);
    url.searchParams.set("analysis_id", analysisId);
    return withExperimentContext(url.toString(), window.location.search);
  }

  function createAnalysisId() {
    const params = new URLSearchParams(window.location.search);
    const explicit = normalizeAnalysisId(
      params.get("analysis_id") || params.get("analysisId"),
    );
    const generated = (
      `analysis-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 10)}`
    );
    const id = explicit || generated;
    window.__verbalvis_analysis_id = id;
    return id;
  }

  function normalizeAnalysisId(value) {
    return String(value || "")
      .trim()
      .replace(/[^A-Za-z0-9_.-]/g, "-")
      .slice(0, 80);
  }

  onBeforeUnmount(disconnect);

  return {
    toolRunning,
    runtime,
    connect,
    sendAudio,
    disconnect,
  };
}
