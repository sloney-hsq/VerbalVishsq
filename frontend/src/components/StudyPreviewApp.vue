<template>
  <main class="study-preview">
    <header class="study-preview__controls">
      <div><strong>Synthetic study UI fixture</strong><span>No provider, formal assignment, timing authority, or study record is active.</span></div>
      <label>Preview state
        <select v-model="selected"><option v-for="(_,key) in STUDY_PREVIEW_STATES" :key="key" :value="key">{{ labels[key] }}</option></select>
      </label>
    </header>
    <div v-if="error" class="study-preview__error" role="alert">{{ error }}</div>
    <Dashboard v-else preview-mode :study-preview-state="STUDY_PREVIEW_STATES[selected]" />
  </main>
</template>

<script setup>
import {onMounted,ref} from 'vue';
import Dashboard from './Dashboard.vue';
import {useDashboardStore} from '../stores/dashboard.js';
import {STUDY_PREVIEW_STATES} from '../studyPreviewFixtures.js';

const selected = ref(new URLSearchParams(window.location.search).get('state') || 'ready');
if (!Object.hasOwn(STUDY_PREVIEW_STATES,selected.value)) selected.value = 'ready';
const error = ref('');
const store = useDashboardStore();
const labels = {ready:'Ready',exploring:'Exploring',freeze_pending:'Freeze pending',answering:'Answering',completed:'Completed + questionnaire',error:'Error / aborted'};

onMounted(async () => {
  try {
    const response = await fetch('/__visual-check-data');
    if (!response.ok) throw new Error(`Synthetic chart fixture failed to load (${response.status}).`);
    const views = Object.values(await response.json());
    store.initViews(views,1,{filters:[]});
  } catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason); }
});
</script>

<style scoped>
.study-preview{display:grid;width:100%;height:100dvh;grid-template-rows:auto minmax(0,1fr);overflow:hidden;background:#eef2f7}.study-preview__controls{z-index:5;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:9px 16px;border-bottom:1px solid #cbd5e1;background:#182235;color:#fff;font:13px/1.35 Inter,'Segoe UI',sans-serif}.study-preview__controls div,.study-preview__controls label{display:flex;align-items:center;gap:10px}.study-preview__controls span{color:#cbd5e1}.study-preview__controls select{margin-left:5px;padding:5px 8px;border:1px solid #64748b;border-radius:6px;background:#fff;color:#172033;font:inherit}.study-preview__error{padding:24px;color:#9e2d28;font:16px/1.5 'Segoe UI',sans-serif}.study-preview :deep(.workspace){height:100%;min-height:0}
@media(max-width:760px){.study-preview__controls{align-items:flex-start;flex-direction:column}.study-preview__controls div{align-items:flex-start;flex-direction:column;gap:2px}}
</style>
