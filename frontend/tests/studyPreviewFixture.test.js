import test from 'node:test';
import assert from 'node:assert/strict';

import { STUDY_PREVIEW_STATES } from '../src/studyPreviewFixtures.js';

test('synthetic preview covers each study UI state without provider authority', () => {
  assert.deepEqual(Object.keys(STUDY_PREVIEW_STATES), ['ready','exploring','freeze_pending','answering','completed','error']);
  assert.equal(STUDY_PREVIEW_STATES.ready.task, null);
  assert.equal(STUDY_PREVIEW_STATES.exploring.phase, 'exploring');
  assert.equal(STUDY_PREVIEW_STATES.freeze_pending.freeze_status, 'pending');
  assert.equal(STUDY_PREVIEW_STATES.answering.freeze_status, 'ready');
  assert.deepEqual(STUDY_PREVIEW_STATES.completed.allowed_actions, ['questionnaire.submit']);
  assert.equal(STUDY_PREVIEW_STATES.error.phase, 'aborted');
  assert.equal(JSON.stringify(STUDY_PREVIEW_STATES).includes('condition'), false);
});
