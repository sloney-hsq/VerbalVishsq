<template>
  <section v-if="state" class="study-panel" :class="`study-panel--${state.phase}`" aria-label="Study trial">
    <header class="study-panel__header">
      <div>
        <p class="study-panel__eyebrow">FORMAL STUDY · ONE TASK</p>
        <h2>{{ phaseTitle }}</h2>
      </div>
      <time v-if="displayRemaining !== null" class="study-panel__timer" aria-label="Time remaining">{{ formattedRemaining }}</time>
    </header>

    <div v-if="state.phase === 'preparing'" class="study-panel__notice" role="status">
      Preparing the voice session and initial evidence. The task will remain hidden until the trial starts.
    </div>

    <div v-else-if="state.phase === 'ready'" class="study-panel__ready">
      <p>Your assigned voice session is ready. Start only when the facilitator asks you to begin.</p>
      <button type="button" class="study-panel__primary" :disabled="!connected || !allows('trial.start')" @click="send('trial.start')">Start task</button>
    </div>

    <article v-if="taskVisible" class="study-task">
      <p class="study-task__label">Assigned task</p>
      <h3>{{ state.task.title }}</h3>
      <p>{{ state.task.prompt || state.task.description }}</p>
    </article>

    <div v-if="state.phase === 'exploring'" class="study-panel__voice-controls">
      <p>Use the microphone to explore the task. The timer is a display of server-provided time; the server decides when exploration closes.</p>
      <button type="button" class="study-panel__stop" :disabled="!connected || !allows('control.stop')" @click="send('control.stop')">Stop</button>
    </div>

    <div v-if="state.phase === 'answering' && state.freeze_status !== 'ready'" class="study-panel__notice" role="status">
      <strong>Freezing your final evidence…</strong>
      <span>Please wait while the final dashboard render and evidence record are confirmed.</span>
    </div>

    <form v-if="answerReady" class="study-answer" @submit.prevent="submitAnswer">
      <fieldset :disabled="!connected || state.answer_status === 'submitted'">
        <legend>Final answer</legend>
        <label>Conclusion<textarea v-model="draft.conclusion" maxlength="8000" rows="4" @input="markChanged" /></label>
        <fieldset class="study-evidence">
          <legend>Evidence</legend>
          <p>Select the frozen chart versions that support your conclusion.</p>
          <label v-for="evidence in evidenceOptions" :key="evidence.id" class="study-evidence__option">
            <input v-model="draft.evidence_refs" type="checkbox" :value="evidence.id" @change="markChanged" />
            <span>{{ evidence.label }}</span>
          </label>
          <span v-if="!evidenceOptions.length" class="study-answer__error">No frozen evidence is available to reference.</span>
        </fieldset>
        <label>Limitations<textarea v-model="draft.limitations" maxlength="8000" rows="3" @input="markChanged" /></label>
        <p class="study-answer__count" :class="{'is-over':answerLength > 8000}">{{ answerLength }} / 8,000 characters</p>
        <div class="study-answer__actions">
          <button type="button" :disabled="!canSave" @click="saveAnswer">Save draft</button>
          <button type="submit" class="study-panel__primary" :disabled="!canSubmit">Submit final answer</button>
          <span v-if="showSaved" class="study-answer__saved" role="status">Saved</span>
          <span v-else-if="receiptError" class="study-answer__error" role="alert">{{ receiptError }}</span>
        </div>
      </fieldset>
    </form>

    <form v-if="questionnaireVisible" class="study-questionnaire" @submit.prevent="submitQuestionnaire">
      <fieldset :disabled="!connected || !allows('questionnaire.submit') || questionnairePending">
        <legend>Experience questionnaire</legend>
        <p>For each statement, choose 1 (Strongly disagree) through 7 (Strongly agree).</p>
        <label v-for="item in questionnaireItems" :key="item.key">
          <span>{{ item.label }}</span>
          <select v-model.number="questionnaire[item.key]" required>
            <option disabled value="">Select</option>
            <option v-for="score in 7" :key="score" :value="score">{{ score }}</option>
          </select>
        </label>
        <button type="submit" class="study-panel__primary" :disabled="!questionnaireComplete || questionnairePending">{{ questionnairePending ? 'Submitting…' : 'Submit questionnaire' }}</button>
        <span v-if="questionnaireReceiptError" class="study-answer__error" role="alert">{{ questionnaireReceiptError }}</span>
      </fieldset>
    </form>

    <div v-if="state.phase === 'completed' && !questionnaireVisible" class="study-panel__notice" role="status"><strong>Trial complete.</strong> Your response has been recorded.</div>
    <div v-if="state.phase === 'aborted'" class="study-panel__notice study-panel__notice--error" role="alert"><strong>The trial has stopped.</strong> Please contact the facilitator.</div>
    <p v-if="!connected" class="study-panel__notice study-panel__notice--error" role="alert">Connection lost. Your unsaved text remains on this screen; this trial will not restart automatically.</p>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue';
import { normalizeEvidenceRefs, selectedEvidenceRefs, studyQuestionnaireVisible, studyTaskVisible } from '../studyProtocol.js';

const props = defineProps({
  state: { type:Object, default:null },
  connected: { type:Boolean, default:false },
  answerSaved: { type:Boolean, default:false },
  receipt: { type:Object, default:null },
});
const emit = defineEmits(['control']);
const draft = reactive({ conclusion:'', evidence_refs:[], limitations:'' });
const questionnaire = reactive({ continuity:'', control:'', effort:'', waiting_interference:'' });
const draftVersion = ref(0);
const editVersion = ref(0);
const pendingSave = ref(null);
const locallyDirty = ref(false);
const questionnairePending = ref(false);
const questionnaireSubmitted = ref(props.receipt?.event_type === 'questionnaire.submit' && props.receipt?.status === 'accepted');
const displayRemaining = ref(null);
let countdown = null;
let presented = false;

const taskVisible = computed(() => studyTaskVisible(props.state || {}));
const answerReady = computed(() => props.state?.phase === 'answering' && props.state?.freeze_status === 'ready');
const questionnaireVisible = computed(() => !questionnaireSubmitted.value && studyQuestionnaireVisible(props.state || {}));
const showSaved = computed(() => props.answerSaved && !locallyDirty.value);
const answerLength = computed(() => draft.conclusion.length + draft.limitations.length);
const canSave = computed(() => props.connected && allows('answer.save') && answerLength.value <= 8000);
const canSubmit = computed(() => props.connected && allows('answer.submit') && answerLength.value <= 8000);
const questionnaireComplete = computed(() => questionnaireItems.every(item => Number.isInteger(questionnaire[item.key])));
const formattedRemaining = computed(() => {
  const seconds = Math.max(0, Math.ceil((displayRemaining.value || 0) / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
});
const phaseTitle = computed(() => ({
  preparing:'Preparing session', ready:'Ready to begin', exploring:'Voice exploration',
  answering:props.state?.freeze_status === 'ready' ? 'Final response' : 'Securing final evidence',
  completed:'Completed', aborted:'Trial stopped',
}[props.state?.phase] || 'Study trial'));
const evidenceOptions = computed(() => normalizeEvidenceRefs(props.state?.evidence_refs_ready));
const receiptError = computed(() => props.receipt?.event_type?.startsWith('answer.') && props.receipt.status !== 'accepted'
  ? `Not saved (${props.receipt.error_code || props.receipt.status}).` : '');
const questionnaireReceiptError = computed(() => props.receipt?.event_type === 'questionnaire.submit' && props.receipt.status !== 'accepted'
  ? `Questionnaire not submitted (${props.receipt.error_code || props.receipt.status}). Please review your answers and retry.` : '');
const questionnaireItems = [
  {key:'continuity',label:'I could maintain my train of thought while using the system.'},
  {key:'control',label:'I felt in control of the analysis.'},
  {key:'effort',label:'Expressing my analysis requests required substantial effort.'},
  {key:'waiting_interference',label:'Waiting for the system disrupted my analysis.'},
];

watch(() => [props.state?.phase, props.state?.remaining_ms], () => {
  clearInterval(countdown);
  displayRemaining.value = Number.isFinite(props.state?.remaining_ms) ? props.state.remaining_ms : null;
  if (displayRemaining.value === null || import.meta.env.SSR) return;
  const initial = displayRemaining.value;
  const started = performance.now();
  countdown = setInterval(() => { displayRemaining.value = Math.max(0, initial - (performance.now() - started)); }, 250);
}, {immediate:true});
watch([taskVisible, () => props.connected], ([visible, connected]) => {
  if (visible && connected && !presented) send('trial.task_presented', {}, sent => { if (sent) presented = true; });
}, {immediate:true});
watch(() => props.receipt, receipt => {
  if (receipt?.event_type === 'questionnaire.submit') {
    questionnairePending.value = false;
    if (receipt.status === 'accepted') questionnaireSubmitted.value = true;
  }
  if (receipt?.event_type !== 'answer.save' || receipt.status !== 'accepted') return;
  if (receipt.receipt?.draft_version !== pendingSave.value?.draftVersion) return;
  if (editVersion.value !== pendingSave.value.editVersion) return;
  locallyDirty.value = false;
});
onBeforeUnmount(() => clearInterval(countdown));

function allows(type) { return props.state?.allowed_actions?.includes(type) === true; }
function send(type, payload={}, report=null) { emit('control', type, payload, report); }
function markChanged() { editVersion.value += 1; locallyDirty.value = true; }
function answerPayload() { return {draft_version:draftVersion.value,conclusion:draft.conclusion,evidence_refs:selectedEvidenceRefs(evidenceOptions.value,draft.evidence_refs),limitations:draft.limitations}; }
function saveAnswer() { draftVersion.value += 1; pendingSave.value = {draftVersion:draftVersion.value,editVersion:editVersion.value}; send('answer.save', answerPayload()); }
function submitAnswer() { const {draft_version:_ignored,...answer} = answerPayload(); send('answer.submit', {...answer,submission_id:crypto.randomUUID()}); }
function submitQuestionnaire() { questionnairePending.value = true; send('questionnaire.submit', {responses:{...questionnaire}}); }
</script>

<style scoped>
.study-panel{margin:0 0 18px;padding:clamp(14px,.55vw,22px);border:1px solid var(--vv-border,#dfe6ef);border-radius:14px;background:var(--vv-surface,#fff);color:var(--vv-text,#172033);box-shadow:0 2px 8px rgba(15,23,42,.04)}
.study-panel__header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:12px}.study-panel__header h2{margin:2px 0 0;font-size:clamp(18px,.58vw,24px)}.study-panel__eyebrow,.study-task__label{margin:0;color:var(--vv-muted,#64748b);font-size:11px;font-weight:800;letter-spacing:.12em}.study-panel__timer{padding:6px 10px;border-radius:8px;background:#eef5ff;color:#174ea6;font-size:clamp(18px,.55vw,24px);font-variant-numeric:tabular-nums;font-weight:750}.study-panel__ready,.study-panel__voice-controls,.study-answer__actions{display:flex;align-items:center;justify-content:space-between;gap:14px}.study-panel__ready p,.study-panel__voice-controls p{margin:0;max-width:76ch;color:var(--vv-muted,#64748b)}button{min-height:36px;padding:7px 13px;border:1px solid var(--vv-border,#cbd5e1);border-radius:8px;background:#fff;color:var(--vv-text,#334155);font:inherit;font-weight:700;cursor:pointer}button:disabled{cursor:not-allowed;opacity:.5}.study-panel__primary{border-color:#2563eb;background:#2563eb;color:#fff}.study-panel__stop{border-color:#efb0ad;color:#a62922}.study-task{margin:12px 0;padding:13px 15px;border-left:4px solid #2563eb;border-radius:8px;background:#f5f8fc}.study-task h3{margin:4px 0 6px;font-size:17px}.study-task p:last-child{margin:0;line-height:1.55}.study-panel__notice{display:flex;gap:8px;flex-wrap:wrap;padding:12px 14px;border:1px solid #bfd4f7;border-radius:9px;background:#f1f7ff;color:#315c9a}.study-panel__notice--error{border-color:#f1b5b1;background:#fff3f2;color:#9e2d28}.study-answer,.study-questionnaire{margin-top:14px}.study-answer>fieldset,.study-questionnaire>fieldset{display:grid;margin:0;padding:0;gap:12px;border:0}.study-answer legend,.study-questionnaire legend{font-size:17px;font-weight:750}.study-answer label,.study-questionnaire label{display:grid;gap:6px;font-weight:650}.study-answer textarea,.study-answer input[type=text],.study-questionnaire select{width:100%;padding:9px 10px;border:1px solid var(--vv-border,#cbd5e1);border-radius:8px;background:#fff;color:inherit;font:inherit}.study-evidence{display:grid;margin:0;padding:10px 12px;gap:8px;border:1px solid var(--vv-border,#dfe6ef);border-radius:9px}.study-evidence p{margin:0;color:var(--vv-muted,#64748b);font-weight:400}.study-evidence__option{display:flex!important;align-items:center;gap:8px!important;font-weight:500!important}.study-answer__count{margin:0;color:var(--vv-muted,#64748b);text-align:right}.study-answer__count.is-over,.study-answer__error{color:#b42318}.study-answer__saved{color:#277447;font-weight:750}.study-questionnaire label{grid-template-columns:minmax(0,1fr) 90px;align-items:center}.study-questionnaire p{margin:0;color:var(--vv-muted,#64748b)}
@media(max-width:900px){.study-panel__ready,.study-panel__voice-controls,.study-answer__actions{align-items:stretch;flex-direction:column}.study-panel__ready button,.study-panel__voice-controls button{align-self:flex-start}.study-questionnaire label{grid-template-columns:minmax(0,1fr) 76px}}
</style>
