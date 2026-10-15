import { onBeforeUnmount, ref } from "vue";

const DEFAULT_INPUT_SAMPLE_RATE = 16000;
const DEFAULT_OUTPUT_SAMPLE_RATE = 24000;
const CHUNK_MS = 40;

/**
 * Microphone PCM capture and assistant PCM playback.
 *
 * Hard playback invariant:
 *   audio from at most one assistant response may be scheduled at any time.
 *
 * Turn detection belongs to Qwen Semantic VAD. This composable intentionally
 * does not implement a second browser-side VAD or backchannel classifier.
 */
export function useAudio(options = {}) {
  const inputSampleRate = Number(options.inputSampleRate) || DEFAULT_INPUT_SAMPLE_RATE;
  const outputSampleRate = Number(options.outputSampleRate) || DEFAULT_OUTPUT_SAMPLE_RATE;
  const chunkSize = Math.round((inputSampleRate * CHUNK_MS) / 1000);

  const isRecording = ref(false);
  const isMicReady = ref(false);
  const captureBlocked = ref(false);

  let captureContext = null;
  let mediaStream = null;
  let sourceNode = null;
  let workletNode = null;
  let setupPromise = null;
  let onAudioChunk = null;

  let playbackContext = null;
  let playbackGain = null;
  let nextPlayTime = 0;
  let currentResponseId = null;
  let currentPlayback = null;
  let assistantAudioBlocked = false;
  let onPlaybackIdle = null;
  const activeSources = new Set();
  const invalidatedResponseIds = new Set();
  const flushedResponseIds = new Set();

  // ------------------------------------------------------------------
  // Microphone capture
  // ------------------------------------------------------------------

  async function startRecording(callback) {
    onAudioChunk = typeof callback === "function" ? callback : callback?.onChunk || null;
    await ensureCapture();
    if (captureContext?.state === "suspended") await captureContext.resume();
    isRecording.value = true;
  }

  function stopRecording() {
    isRecording.value = false;
  }

  function setCaptureBlocked(blocked) {
    captureBlocked.value = Boolean(blocked);
  }

  async function ensureCapture() {
    if (captureContext && mediaStream && workletNode) return;
    if (setupPromise) return setupPromise;

    setupPromise = (async () => {
      captureContext = new AudioContext({ sampleRate: inputSampleRate });
      const code = `
        const CHUNK_SIZE = ${chunkSize};
        class VerbalVisPCMProcessor extends AudioWorkletProcessor {
          constructor() {
            super();
            this.chunk = new Int16Array(CHUNK_SIZE);
            this.offset = 0;
          }
          process(inputs) {
            const channel = inputs[0] && inputs[0][0];
            if (!channel) return true;
            for (let i = 0; i < channel.length; i += 1) {
              const sample = Math.max(-1, Math.min(1, channel[i]));
              this.chunk[this.offset++] = sample < 0
                ? sample * 0x8000
                : sample * 0x7fff;
              if (this.offset >= CHUNK_SIZE) {
                const output = this.chunk;
                this.port.postMessage(output.buffer, [output.buffer]);
                this.chunk = new Int16Array(CHUNK_SIZE);
                this.offset = 0;
              }
            }
            return true;
          }
        }
        registerProcessor("verbalvis-pcm", VerbalVisPCMProcessor);
      `;
      const blobUrl = URL.createObjectURL(new Blob([code], { type: "application/javascript" }));
      try {
        await captureContext.audioWorklet.addModule(blobUrl);
      } finally {
        URL.revokeObjectURL(blobUrl);
      }

      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: inputSampleRate,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      sourceNode = captureContext.createMediaStreamSource(mediaStream);
      workletNode = new AudioWorkletNode(captureContext, "verbalvis-pcm");
      workletNode.port.onmessage = (event) => {
        if (!isRecording.value || captureBlocked.value || !onAudioChunk) return;
        onAudioChunk(arrayBufferToBase64(event.data));
      };
      sourceNode.connect(workletNode);
      const silentGain = captureContext.createGain();
      silentGain.gain.value = 0;
      workletNode.connect(silentGain);
      silentGain.connect(captureContext.destination);
      isMicReady.value = true;
    })().finally(() => {
      setupPromise = null;
    });

    return setupPromise;
  }

  function disposeRecording() {
    stopRecording();
    workletNode?.disconnect();
    sourceNode?.disconnect();
    mediaStream?.getTracks().forEach((track) => track.stop());
    captureContext?.close().catch(() => {});
    workletNode = null;
    sourceNode = null;
    mediaStream = null;
    captureContext = null;
    onAudioChunk = null;
    isMicReady.value = false;
  }

  // ------------------------------------------------------------------
  // Assistant playback
  // ------------------------------------------------------------------

  function beginAssistantResponse(responseId) {
    if (!responseId) return;

    // Stop B before C becomes current. Assigning C first was the original
    // reason B and C could remain scheduled at the same time.
    if (currentResponseId && currentResponseId !== responseId) {
      stopAssistantAudio({
        responseId: currentResponseId,
        blockNewAudio: false,
        reason: "superseded_by_new_response",
      });
    }
    stopSourcesExcept(responseId);

    currentResponseId = responseId;
    invalidatedResponseIds.delete(responseId);
    flushedResponseIds.delete(responseId);
    assistantAudioBlocked = false;
    const context = ensurePlaybackContext();
    nextPlayTime = Math.max(nextPlayTime, context.currentTime);
  }

  function enqueue(base64Pcm, metadata = {}) {
    const responseId = metadata.response_id || metadata.responseId || null;
    if (!responseId || assistantAudioBlocked) return false;
    if (invalidatedResponseIds.has(responseId)) return false;

    if (!currentResponseId) beginAssistantResponse(responseId);
    if (responseId !== currentResponseId) return false;

    const context = ensurePlaybackContext();
    const samples = decodePcm16(base64Pcm);
    if (!samples.length) return false;

    const buffer = context.createBuffer(1, samples.length, outputSampleRate);
    buffer.getChannelData(0).set(samples);

    const startAt = Math.max(context.currentTime, nextPlayTime);
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(playbackGain || context.destination);

    const record = {
      source,
      responseId,
      itemId: metadata.item_id || metadata.itemId || null,
      contentIndex: metadata.content_index ?? metadata.contentIndex ?? 0,
      startAt,
      endAt: startAt + buffer.duration,
      stoppedManually: false,
    };
    activeSources.add(record);
    trackPlayback(record);

    source.onended = () => {
      activeSources.delete(record);
      if (record.stoppedManually) return;
      maybeFinishPlayback(responseId);
    };

    source.start(startAt);
    nextPlayTime = record.endAt;
    return true;
  }

  function flush(metadata = {}) {
    const responseId = metadata.response_id || metadata.responseId || currentResponseId;
    if (!responseId) return;
    flushedResponseIds.add(responseId);
    maybeFinishPlayback(responseId);
  }

  function maybeFinishPlayback(responseId) {
    if (responseId !== currentResponseId) return;
    if (!flushedResponseIds.has(responseId)) return;
    if (hasActiveSource(responseId)) return;

    const playbackCursor = getPlaybackCursor();
    flushedResponseIds.delete(responseId);
    currentResponseId = null;
    currentPlayback = null;
    nextPlayTime = playbackContext?.currentTime || 0;
    onPlaybackIdle?.({
      responseId,
      playbackCursor,
      reason: "natural_end",
    });
  }

  function stopAssistantAudio({ responseId = null, blockNewAudio = true, reason = "interrupted" } = {}) {
    const targetResponseId = responseId || currentResponseId;
    const playbackCursor = getPlaybackCursor();

    if (targetResponseId) {
      invalidatedResponseIds.add(targetResponseId);
      flushedResponseIds.delete(targetResponseId);
    }
    if (blockNewAudio) assistantAudioBlocked = true;

    for (const record of Array.from(activeSources)) {
      if (targetResponseId && record.responseId !== targetResponseId) continue;
      record.stoppedManually = true;
      try {
        record.source.stop();
      } catch (_) {
        // The source may already have ended.
      }
      activeSources.delete(record);
    }

    if (!targetResponseId || currentResponseId === targetResponseId) {
      currentResponseId = null;
      currentPlayback = null;
    }
    nextPlayTime = playbackContext && playbackContext.state !== "closed"
      ? playbackContext.currentTime
      : 0;

    return playbackCursor
      ? { ...playbackCursor, reason }
      : null;
  }

  function stop() {
    return stopAssistantAudio({ blockNewAudio: true, reason: "manual_stop" });
  }

  function stopSourcesExcept(responseId) {
    for (const record of Array.from(activeSources)) {
      if (record.responseId === responseId) continue;
      invalidatedResponseIds.add(record.responseId);
      flushedResponseIds.delete(record.responseId);
      record.stoppedManually = true;
      try {
        record.source.stop();
      } catch (_) {
        // Already ended.
      }
      activeSources.delete(record);
    }
  }

  function ensurePlaybackContext() {
    if (!playbackContext || playbackContext.state === "closed") {
      playbackContext = new AudioContext({ sampleRate: outputSampleRate });
      playbackGain = playbackContext.createGain();
      playbackGain.gain.value = 1;
      playbackGain.connect(playbackContext.destination);
      nextPlayTime = playbackContext.currentTime;
    } else if (playbackContext.state === "suspended") {
      playbackContext.resume().catch(() => {});
    }
    return playbackContext;
  }

  function hasActiveSource(responseId) {
    return Array.from(activeSources).some((record) => record.responseId === responseId);
  }

  function trackPlayback(record) {
    if (
      !currentPlayback ||
      currentPlayback.responseId !== record.responseId ||
      currentPlayback.itemId !== record.itemId ||
      currentPlayback.contentIndex !== record.contentIndex
    ) {
      currentPlayback = {
        responseId: record.responseId,
        itemId: record.itemId,
        contentIndex: record.contentIndex,
        startAt: record.startAt,
        endAt: record.endAt,
      };
      return;
    }
    currentPlayback.endAt = Math.max(currentPlayback.endAt, record.endAt);
  }

  function getPlaybackCursor() {
    if (!playbackContext || !currentPlayback?.itemId) return null;
    const totalMs = Math.max(0, (currentPlayback.endAt - currentPlayback.startAt) * 1000);
    const elapsedMs = Math.max(
      0,
      Math.min(totalMs, (playbackContext.currentTime - currentPlayback.startAt) * 1000),
    );
    return {
      item_id: currentPlayback.itemId,
      content_index: currentPlayback.contentIndex,
      audio_end_ms: Math.round(elapsedMs),
    };
  }

  function setPlaybackIdleHandler(callback) {
    onPlaybackIdle = typeof callback === "function" ? callback : null;
  }

  function disposePlayback() {
    stopAssistantAudio({ blockNewAudio: true, reason: "dispose" });
    playbackContext?.close().catch(() => {});
    playbackContext = null;
    playbackGain = null;
    invalidatedResponseIds.clear();
    flushedResponseIds.clear();
    onPlaybackIdle = null;
  }

  // ------------------------------------------------------------------
  // Encoding helpers
  // ------------------------------------------------------------------

  function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.length; i += 1) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }

  function decodePcm16(base64Pcm) {
    const binary = atob(base64Pcm || "");
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    const int16 = new Int16Array(bytes.buffer);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i += 1) float32[i] = int16[i] / 0x8000;
    return float32;
  }

  onBeforeUnmount(() => {
    disposeRecording();
    disposePlayback();
  });

  return {
    isRecording,
    isMicReady,
    captureBlocked,
    inputSampleRate,
    outputSampleRate,
    startRecording,
    stopRecording,
    setCaptureBlocked,
    beginAssistantResponse,
    enqueue,
    flush,
    stop,
    stopAssistantAudio,
    getPlaybackCursor,
    setPlaybackIdleHandler,
  };
}
