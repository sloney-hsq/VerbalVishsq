import test from 'node:test';
import assert from 'node:assert/strict';
import { createSSRApp, h } from 'vue';
import { createPinia } from 'pinia';
import { renderToString } from '@vue/server-renderer';
import { createServer } from 'vite';

const task = {title:'Investigate delivery and review evidence',prompt:'Assess the relationship and note important limitations.'};
const base = {freeze_status:null,remaining_ms:null,task:null,answer_status:null,evidence_refs_ready:[],allowed_actions:[]};

function browserLocation(t) {
  const previous = globalThis.window;
  globalThis.window = { location: { search: '' } };
  t.after(() => { if (previous === undefined) delete globalThis.window; else globalThis.window = previous; });
}

async function load(t) {
  const vite = await createServer({server:{middlewareMode:true},appType:'custom',logLevel:'silent'});
  t.after(() => vite.close());
  return {
    StudyPanel:(await vite.ssrLoadModule('/src/components/StudyPanel.vue')).default,
    Dashboard:(await vite.ssrLoadModule('/src/components/Dashboard.vue')).default,
    useRuntimeStore:(await vite.ssrLoadModule('/src/stores/runtime.js')).useRuntimeStore,
  };
}

async function renderPanel(Component, state) {
  return renderToString(createSSRApp({render:() => h(Component,{state,connected:true})}));
}

test('single formal trial hides the task before start and exposes no early finish', async t => {
  const {StudyPanel} = await load(t);
  const ready = await renderPanel(StudyPanel,{...base,phase:'ready',task:{title:'Must remain hidden'},allowed_actions:['trial.start']});
  assert.match(ready,/Start task/);
  assert.doesNotMatch(ready,/Must remain hidden|Finish task|condition|second task/i);

  const exploring = await renderPanel(StudyPanel,{...base,phase:'exploring',remaining_ms:600000,task,allowed_actions:['control.stop']});
  assert.match(exploring,/Investigate delivery and review evidence/);
  assert.match(exploring,/>Stop</);
  assert.doesNotMatch(exploring,/<textarea|Finish task|Start another/i);
});

test('task-presented observation waits for an available study transport', async t => {
  const {StudyPanel} = await load(t);
  const events = [];
  const state = {...base,phase:'exploring',remaining_ms:600000,task,allowed_actions:['control.stop']};
  await renderToString(createSSRApp({render:() => h(StudyPanel,{
    state,connected:false,onControl:(type,payload,report) => { events.push(type); report?.(false); },
  })}));
  assert.deepEqual(events, []);

  await renderToString(createSSRApp({render:() => h(StudyPanel,{
    state,connected:true,onControl:(type,payload,report) => { events.push(type); report?.(true); },
  })}));
  assert.deepEqual(events, ['trial.task_presented']);
});

test('freeze pending blocks answers, then ready exposes only final-answer fields', async t => {
  const {StudyPanel} = await load(t);
  const pending = await renderPanel(StudyPanel,{...base,phase:'answering',freeze_status:'pending',task});
  assert.match(pending,/Freezing your final evidence/);
  assert.doesNotMatch(pending,/<textarea/);

  const answering = await renderPanel(StudyPanel,{...base,phase:'answering',freeze_status:'ready',remaining_ms:180000,task,
    evidence_refs_ready:[{revision:4,artifact_id:'artifact-4'}],allowed_actions:['answer.save','answer.submit']});
  assert.match(answering,/Conclusion/);
  assert.match(answering,/Evidence/);
  assert.match(answering,/Dashboard revision 4/);
  assert.match(answering,/Limitations/);
  assert.equal((answering.match(/<textarea/g) || []).length,2);
});

test('completed answer can still collect the four-item questionnaire', async t => {
  const {StudyPanel} = await load(t);
  const completed = await renderPanel(StudyPanel,{...base,phase:'completed',task,answer_status:'submitted',allowed_actions:['questionnaire.submit']});
  assert.match(completed,/Experience questionnaire/);
  assert.match(completed,/maintain my train of thought/);
  assert.match(completed,/felt in control/);
  assert.match(completed,/required substantial effort/);
  assert.match(completed,/Waiting for the system disrupted/);
  assert.doesNotMatch(completed,/Trial complete/);
});

test('questionnaire receipt exposes a visible terminal acknowledgement or retry error', async t => {
  const {StudyPanel} = await load(t);
  const state = {...base,phase:'completed',task,answer_status:'submitted',allowed_actions:['questionnaire.submit']};
  const accepted = await renderToString(createSSRApp({render:() => h(StudyPanel,{
    state,connected:true,receipt:{event_type:'questionnaire.submit',status:'accepted'},
  })}));
  assert.match(accepted,/Trial complete/);
  assert.doesNotMatch(accepted,/Experience questionnaire/);

  const rejected = await renderToString(createSSRApp({render:() => h(StudyPanel,{
    state,connected:true,receipt:{event_type:'questionnaire.submit',status:'conflict',error_code:'questionnaire_conflict'},
  })}));
  assert.match(rejected,/Experience questionnaire/);
  assert.match(rejected,/questionnaire_conflict/);
});

test('answering keeps the chart workspace beside a dominant study rail', async t => {
  browserLocation(t);
  const {Dashboard} = await load(t);
  const state = {...base,phase:'answering',freeze_status:'ready',remaining_ms:180000,task,
    evidence_refs_ready:[{revision:4,artifact_id:'artifact-4'}],allowed_actions:['answer.save','answer.submit']};
  const app = createSSRApp({render:() => h(Dashboard,{previewMode:true,studyPreviewState:state})});
  app.use(createPinia());
  const html = await renderToString(app);

  assert.match(html,/conversation-panel--study-dominant/);
  assert.ok(html.indexOf('aria-label="Analytical dashboard"') < html.indexOf('aria-label="Study trial"'));
});

test('both assigned voice policies render the same controls and chart area', async t => {
  browserLocation(t);
  const {Dashboard,useRuntimeStore} = await load(t);
  const renderFor = async condition => {
    const pinia = createPinia();
    useRuntimeStore(pinia).applyInputPolicy({type:'input_policy',seq:1,condition,phase:'ready',accepts_audio:true});
    const state = {...base,phase:'exploring',remaining_ms:600000,task,allowed_actions:['control.stop']};
    const app = createSSRApp({render:() => h(Dashboard,{previewMode:true,studyPreviewState:state})});
    app.use(pinia);
    return renderToString(app);
  };
  const first = await renderFor('revision_enabled');
  const second = await renderFor('turn_taking');
  for (const html of [first,second]) {
    assert.match(html,/workspace-mic/);
    assert.match(html,/>Stop</);
    assert.match(html,/aria-label="Analytical dashboard"/);
    assert.doesNotMatch(html,/Type your analysis|condition switch|Finish task/i);
  }
  assert.equal(first,second);
});
