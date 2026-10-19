<template>
  <main class="workspace workspace--conversation-bottom" :class="{ 'workspace--conversation-hidden': timelineCollapsed, 'workspace--study': activeStudyState, 'workspace--study-dominant': studyPanelDominant }">
    <header class="workspace-topbar">
      <div class="workspace-brand">
        <span class="workspace-brand__mark" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></span>
        <h1>VerbalVis</h1>
      </div>
      <div class="workspace-session" :title="sessionTitle" role="status">
        <span class="workspace-status-dot" :class="statusDotClass"></span><span>{{ phaseLabel }}</span>
      </div>
      <div class="workspace-summary" aria-label="Analysis overview">
        <h2 class="workspace-view-count">{{ store.views.length }} {{ store.views.length === 1 ? 'view' : 'views' }}</h2>
        <div class="workspace-scope"><span class="workspace-scope__dot"></span><span>{{ store.activeFilters.length ? `${store.activeFilters.length} active filters` : 'All data' }}</span><span v-if="ws.runtime.filteredRows !== null">· {{ formatCount(ws.runtime.filteredRows) }} records</span></div>
      </div>
      <div class="workspace-topbar__actions">
        <button class="workspace-icon-button" type="button" :disabled="Boolean(activeStudyState)" :aria-expanded="!timelineCollapsed" :aria-label="activeStudyState ? 'Study panel remains visible during the formal trial' : timelineCollapsed ? 'Show conversation' : 'Hide conversation'" aria-controls="conversation-panel" @click="timelineCollapsed = !timelineCollapsed">
          <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M15 4v16" /></svg><span>{{ activeStudyState ? 'Study panel' : timelineCollapsed ? 'Show conversation' : 'Hide conversation' }}</span>
        </button>
        <button v-if="!previewMode || activeStudyState" class="workspace-mic" :class="{ 'workspace-mic--active': audio.isRecording.value }" :disabled="micDisabled" :aria-pressed="audio.isRecording.value" type="button" @click="toggleMicrophone">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z" /><path d="M18 11a6 6 0 0 1-12 0M12 17v4M9 21h6" /></svg><span>{{ micLabel }}</span>
        </button>
      </div>
    </header>
    <div class="workspace-layout">
      <section class="analysis-workspace" aria-label="Analysis workspace">
        <div v-if="store.activeFilters.length" class="workspace-filters" aria-label="Current analysis filters"><span v-for="(filter, index) in store.activeFilters" :key="`${filter.field}-${index}`" :title="filterLabel(filter)">{{ filterLabel(filter) }}</span></div>
        <div v-if="inputWait || ws.runtime.lastToolError || ws.runtime.configurationError" class="workspace-notice" role="status"><span v-if="inputWait">Microphone paused. Please wait for your turn.</span><span v-if="ws.runtime.lastToolError">{{ ws.runtime.lastToolError }}</span><span v-if="ws.runtime.configurationError">{{ ws.runtime.configurationError }}</span></div>
        <div v-if="!store.views.length" class="workspace-empty"><svg viewBox="0 0 64 64" aria-hidden="true"><path d="M12 12v40h42M22 42V30m11 12V19m11 23V26" /></svg><h3>Your analysis starts here</h3><p>{{ emptyStateMessage }}</p></div>
        <section v-show="store.views.length" ref="chartGrid" v-chart-grid class="chart-grid" aria-label="Analytical dashboard"><ChartSlot v-for="view in store.views" :key="view.id" :view="view" :display-number="displayNumbers[view.id]" :available-width="chartGridWidth" :render-request="ws.runtime.renderEnvelope" @rendered="handleChartRender('rendered', $event)" @render-failed="handleChartRender('render-failed', $event)" /></section>
      </section>
      <aside v-show="!timelineCollapsed" id="conversation-panel" class="conversation-panel" :class="{'conversation-panel--study':activeStudyState,'conversation-panel--study-dominant':studyPanelDominant}" :aria-label="activeStudyState ? 'Study trial and session conversation' : 'Session conversation'">
        <div v-if="activeStudyState" class="study-panel-host"><StudyPanel :state="activeStudyState" :connected="studyConnected" :answer-saved="ws.runtime.answerSaved" :receipt="ws.runtime.studyReceipt" @control="handleStudyControl" /></div>
        <header v-if="!studyPanelDominant" class="conversation-panel__header"><h2>Conversation</h2><span v-if="conversationGroups.length" class="conversation-panel__count">{{ conversationGroups.length }} turns</span></header>
        <div v-if="!studyPanelDominant" ref="timelineList" class="conversation-panel__list" aria-live="polite" aria-relevant="additions text">
          <p v-if="!conversationGroups.length" class="conversation-empty">No conversation yet.</p>
          <section v-for="group in conversationGroups" :key="group.id" class="conversation-turn">
            <article v-for="item in group.messages" :key="item.id" class="conversation-message" :class="`conversation-message--${item.role}`">
              <header class="conversation-message__meta"><span class="conversation-message__avatar" aria-hidden="true">{{ item.role === 'assistant' ? 'V' : 'Y' }}</span><strong>{{ roleLabel(item) }}</strong><time>{{ formatTime(item.startedAt) }}</time></header>
              <div class="conversation-message__body"><p class="message-text">{{ item.text || statusPlaceholder(item) }}</p><div v-if="item.revisionAccepted || item.superseded || item.status === 'interrupted'" class="conversation-message__feedback"><TranscriptFeedback v-if="item.revisionAccepted" label="Revision accepted" /><TranscriptFeedback v-if="item.superseded" label="Superseded" /><span v-if="item.role === 'assistant' && item.status === 'interrupted'" class="conversation-interrupted">Interrupted</span></div></div>
              <button v-if="group.actions.length && group.actionAnchorId === item.id" class="conversation-actions-toggle" type="button" :aria-expanded="isGroupActionsOpen(group.id)" @click="toggleGroupActions(group.id)"><span aria-hidden="true">{{ isGroupActionsOpen(group.id) ? '−' : '+' }}</span> {{ group.actions.length }} analysis {{ group.actions.length === 1 ? 'step' : 'steps' }}</button>
            </article>
            <div v-if="isGroupActionsOpen(group.id) || (group.actions.length && !group.actionAnchorId)" class="conversation-actions">
              <details v-for="item in group.actions" :key="item.id" class="conversation-action" :class="{ 'conversation-action--error': item.status === 'error' }" :open="item.expanded" @toggle="syncToolDetails(item, $event)"><summary><span class="conversation-action__dot"></span><span>{{ item.summary || formatToolName(item.toolName) }}</span><TranscriptFeedback v-if="item.superseded || item.status === 'superseded'" label="Superseded" /></summary><div class="conversation-action__details"><b>Tool</b><code>{{ item.toolName }}</code><b>Parameters</b><pre>{{ formatParameters(item.parameters) }}</pre><template v-if="item.error"><b>Error</b><code class="conversation-action__error">{{ item.error }}</code></template></div></details>
            </div>
          </section>
        </div>
        <footer v-if="!studyPanelDominant && !previewMode" class="conversation-panel__footer"><span class="conversation-panel__listening-dot" :class="{ 'is-recording': audio.isRecording.value }"></span><span>{{ audio.isRecording.value ? 'Listening to your questions' : 'Use the microphone to start a discussion' }}</span><kbd>Space</kbd></footer>
      </aside>
    </div>
  </main>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import ChartSlot from './ChartSlot.vue';
import StudyPanel from './StudyPanel.vue';
import { TranscriptFeedback } from './TranscriptFeedback.js';
import { useAudio } from '../composables/useAudio';
import { useWebSocket } from '../composables/useWebSocket';
import { useDashboardStore } from '../stores/dashboard';
import { groupTranscriptItems } from '../transcriptGroups';
import { microphoneControl, studyVoiceControl } from '../realtimePolicy';
import { createDashboardRenderTracker } from '../dashboardRenderTracker.js';
import { formatFilter } from '../specFactory.js';
import { vChartGrid, chartDisplayNumbers } from '../chartGrid.js';

const props = defineProps({
  previewMode: { type: Boolean, default: false },
  studyPreviewState: { type:Object, default:null },
});
const store = useDashboardStore();
const displayNumbers = computed(() => chartDisplayNumbers(store.views));
const audio = useAudio();
const ws = useWebSocket(audio);
const renderTracker = createDashboardRenderTracker((type, payload) => ws.sendStudyControl(type, payload));
const timelineList = ref(null);
const chartGrid = ref(null);
const chartGridWidth = ref(0);
let chartGridObserver = null;
const isStartingMic = ref(false);
const timelineCollapsed = ref(false);
const expandedActionGroupIds = ref(new Set());
const phaseLabel = computed(() => props.previewMode ? 'Saved charts · voice offline' : ws.runtime.phaseLabel);
const sessionTitle = computed(() => props.previewMode ? 'Saved analytical results. No live model session.' : `${store.model} · ${store.connectionStatus} · ${phaseLabel.value}`);
const statusDotClass = computed(() => ({ 'workspace-status-dot--connected': !props.previewMode && store.connectionStatus === 'connected', 'workspace-status-dot--connecting': !props.previewMode && store.connectionStatus === 'connecting', 'workspace-status-dot--error': !props.previewMode && ['error', 'configuration_error'].includes(ws.runtime.phase) }));
const micControl = computed(() => microphoneControl({ recording: audio.isRecording.value, starting: isStartingMic.value, captureBlocked: audio.captureBlocked.value, connected: store.connectionStatus === 'connected', sessionReady: store.sessionReady, acceptsAudio: ws.runtime.acceptsAudio }));
const activeStudyState = computed(() => props.studyPreviewState || ws.runtime.studyState);
const studyPanelDominant = computed(() => Boolean(activeStudyState.value && activeStudyState.value.phase !== 'exploring'));
const studyConnected = computed(() => props.studyPreviewState ? true : store.connectionStatus === 'connected');
const studyVoice = computed(() => studyVoiceControl({phase:activeStudyState.value?.phase,freezeStatus:activeStudyState.value?.freeze_status}));
const micDisabled = computed(() => props.previewMode || (activeStudyState.value && !studyVoice.value.microphoneEnabled) || micControl.value.disabled);
const micLabel = computed(() => micControl.value.label);
const inputWait = computed(() => store.sessionReady && ws.runtime.condition === 'turn_taking' && !ws.runtime.acceptsAudio);
const emptyStateMessage = computed(() => ws.runtime.configurationError || (store.connectionStatus === 'connecting' ? 'Connecting to your data and preparing the workspace…' : 'Connect to a session to see your data, then start with a question.'));
const timelineVersion = computed(() => store.transcriptItems.map(item => `${item.id}:${item.text?.length || 0}:${item.status}:${item.revisionAccepted}:${item.superseded}`).join('|'));
const conversationGroups = computed(() => groupTranscriptItems(store.transcriptItems));
watch(timelineVersion, () => nextTick(() => { if (timelineList.value) timelineList.value.scrollTop = timelineList.value.scrollHeight; }));
watch(timelineCollapsed, () => nextTick(() => { if (chartGrid.value) chartGridWidth.value = Math.round(chartGrid.value.clientWidth); }));
watch(activeStudyState, state => { if (state) timelineCollapsed.value = false; });
watch(() => ws.runtime.renderEnvelope, envelope => renderTracker.activate(envelope), {deep:true});
onMounted(() => {
  if (!props.previewMode) ws.connect();
  window.addEventListener('keydown', handleShortcut);
  chartGridObserver = new ResizeObserver(entries => { chartGridWidth.value = Math.round(entries[0]?.contentRect?.width || 0); });
  if (chartGrid.value) chartGridObserver.observe(chartGrid.value);
});
onBeforeUnmount(() => { window.removeEventListener('keydown', handleShortcut); chartGridObserver?.disconnect(); audio.stopRecording(); ws.disconnect(); });
async function startMicrophone() {
  if (micDisabled.value || audio.isRecording.value) return;
  isStartingMic.value = true;
  try { await audio.startRecording(data => ws.sendAudio(data)); }
  catch (error) { console.error('Unable to start microphone', error); audio.stopRecording(); }
  finally { isStartingMic.value = false; }
}
function toggleMicrophone() { if (props.previewMode) return; if (audio.isRecording.value) audio.stopRecording(); else startMicrophone(); }
function handleStudyControl(type, payload, report) {
  const sent = props.studyPreviewState ? true : Boolean(ws.sendStudyControl(type, payload));
  report?.(sent);
}
function handleChartRender(type, payload) { renderTracker.forward(type, payload); }
function isGroupActionsOpen(id) { return expandedActionGroupIds.value.has(id); }
function toggleGroupActions(id) { const next = new Set(expandedActionGroupIds.value); if (next.has(id)) next.delete(id); else next.add(id); expandedActionGroupIds.value = next; }
function syncToolDetails(item, event) { if (Boolean(item.expanded) !== event.target.open) store.toggleToolDetails(item.id); }
function handleShortcut(event) {
  const tag = event.target?.tagName?.toLowerCase();
  if (props.previewMode || event.code !== 'Space' || event.repeat || ['input', 'textarea', 'button', 'summary', 'select', 'a'].includes(tag) || event.target?.isContentEditable) return;
  event.preventDefault(); toggleMicrophone();
}
function roleLabel(item) { return item.role === 'assistant' ? 'VerbalVis' : item.role === 'tool' ? 'Analysis' : 'You'; }
function statusPlaceholder(item) { return item.status === 'listening' ? 'Listening…' : item.status === 'streaming' ? 'Thinking…' : ''; }
function formatTime(timestamp) { return new Intl.DateTimeFormat('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(timestamp || Date.now())); }
function formatToolName(name) { return String(name || 'Analysis step').replace(/_/g, ' '); }
function formatParameters(parameters) { return JSON.stringify(parameters || {}, null, 2); }
function formatCount(value) { return new Intl.NumberFormat('en-US').format(Number(value) || 0); }
function filterLabel(filter) { return formatFilter(filter, store.datasetDescription); }
</script>
<style src="../workspaceTheme.css"></style>
<style src="../chartGrid.css"></style>
<style src="../workspace.css"></style>
<style scoped>
.study-panel-host{flex:0 0 auto;max-height:46%;min-height:0;overflow:auto;padding:12px;border-bottom:1px solid #e9edf3;scrollbar-gutter:stable}
.study-panel-host :deep(.study-panel){margin:0;box-shadow:none}
.conversation-panel--study-dominant .study-panel-host{flex:1 1 auto;max-height:none;border-bottom:0}
@media(max-width:1100px){.study-panel-host{max-height:none}.conversation-panel--study-dominant .study-panel-host{padding:10px}}
</style>
