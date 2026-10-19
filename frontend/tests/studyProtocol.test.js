import test from 'node:test';
import assert from 'node:assert/strict';

import {
  createStudyProtocol,
  createStudyControlEvent,
  dashboardSnapshotFromMessage,
  normalizeEvidenceRefs,
  selectedEvidenceRefs,
  studyQuestionnaireVisible,
  studyTaskVisible,
} from '../src/studyProtocol.js';

test('task remains hidden until the server enters exploring', () => {
  assert.equal(studyTaskVisible({phase:'ready',task:{title:'Secret'}}), false);
  assert.equal(studyTaskVisible({phase:'exploring',task:{title:'Visible'}}), true);
  assert.equal(studyTaskVisible({phase:'answering',task:{title:'Visible'}}), true);
});

test('control whitelist excludes condition switches, typed analysis, and early finish', () => {
  assert.throws(() => createStudyControlEvent('trial.finish', {}, () => 'event-1'));
  assert.throws(() => createStudyControlEvent('analysis.text', {text:'query'}, () => 'event-2'));
  assert.throws(() => createStudyControlEvent('trial.start', {condition:'revision_enabled'}, () => 'event-3'));
  assert.throws(() => createStudyControlEvent('control.stop', {reason:'client-defined'}, () => 'event-4'));
});

test('retry preserves the original event id and payload', () => {
  const event = createStudyControlEvent('answer.save', {draft_version:2, conclusion:'Draft'}, () => 'event-4');
  const retry = createStudyControlEvent('answer.save', {}, () => 'different', event);
  assert.deepEqual(retry, event);
  assert.notEqual(retry, event);
});

test('saved status changes only after a matching server receipt', () => {
  const protocol = createStudyProtocol();
  const event = protocol.queue('answer.save', {draft_version:1, conclusion:'Draft'}, () => 'save-1');
  assert.equal(protocol.answerSaved, false);
  assert.equal(protocol.applyReceipt({type:'study.receipt',client_event_id:'other',event_type:'answer.save',status:'accepted'}), false);
  assert.equal(protocol.answerSaved, false);
  assert.equal(protocol.applyReceipt({type:'study.receipt',client_event_id:event.client_event_id,event_type:'answer.save',status:'accepted',receipt:{draft_version:1}}), true);
  assert.equal(protocol.answerSaved, true);
  protocol.updateDraft({conclusion:'Changed after save'});
  assert.equal(protocol.answerSaved, false);
});

test('an accepted save receipt cannot mark a different draft version saved', () => {
  const protocol = createStudyProtocol();
  const event = protocol.queue('answer.save', {draft_version:2, conclusion:'Newest'}, () => 'save-2');
  assert.equal(protocol.applyReceipt({type:'study.receipt',client_event_id:event.client_event_id,event_type:'answer.save',status:'accepted',receipt:{draft_version:1}}), false);
  assert.equal(protocol.answerSaved, false);
});

test('evidence references preserve the exact ready artifact identity', () => {
  const options = normalizeEvidenceRefs([
    {revision:3,artifact_id:'artifact-3'}, {revision:5,artifact_id:'artifact-5'},
    {revision:5,artifact_id:'bad id'}, 7,
  ]);
  assert.deepEqual(options, [
    {id:'artifact-3',label:'Dashboard revision 3',ref:{revision:3,artifact_id:'artifact-3'}},
    {id:'artifact-5',label:'Dashboard revision 5',ref:{revision:5,artifact_id:'artifact-5'}},
  ]);
  assert.deepEqual(selectedEvidenceRefs(options, ['artifact-5']), [
    {revision:5,artifact_id:'artifact-5'},
  ]);
});

test('questionnaire remains available after answer completion when server allows it', () => {
  assert.equal(studyQuestionnaireVisible({phase:'completed',allowed_actions:['questionnaire.submit']}), true);
  assert.equal(studyQuestionnaireVisible({phase:'completed',allowed_actions:[]}), false);
});

test('questionnaire control uses the server responses envelope', () => {
  const responses = {continuity:7,control:6,effort:3,waiting_interference:2};
  assert.deepEqual(createStudyControlEvent('questionnaire.submit', {responses}, () => 'questionnaire-1'), {
    type:'questionnaire.submit',client_event_id:'questionnaire-1',responses,
  });
  assert.throws(() => createStudyControlEvent('questionnaire.submit', responses, () => 'questionnaire-2'));
});

test('disconnect retains local unsaved fields and never restarts the trial', () => {
  const protocol = createStudyProtocol();
  protocol.updateDraft({conclusion:'Keep this',limitations:'Also keep this'});
  const outgoing = protocol.disconnect();
  assert.deepEqual(outgoing, []);
  assert.deepEqual(protocol.draft, {conclusion:'Keep this',evidence_refs:[],limitations:'Also keep this'});
});

test('frozen dashboard consumes the full snapshot nested in state', () => {
  assert.deepEqual(dashboardSnapshotFromMessage({
    type:'trial.frozen',dashboard_revision:4,
    state:{dashboard_revision:4,views:[{id:'frozen',view_revision:2}],filters:[{field:'region'}]},
  }), {
    viewList:[{id:'frozen',view_revision:2}],
    state:{dashboard_revision:4,views:[{id:'frozen',view_revision:2}],filters:[{field:'region'}]},
    revision:4,digest:null,
  });
});
