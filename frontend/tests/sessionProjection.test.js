import test from 'node:test';
import assert from 'node:assert/strict';
import { SessionProjection } from '../src/sessionProjection.js';

test('revoked response cannot publish a late commit or tool card', () => {
  const p = new SessionProjection();
  assert(p.accept({type:'assistant_response_started',seq:1,response_id:'r'}));
  assert(p.accept({type:'tool_execution_started',seq:2,response_id:'r',batch_id:'b'}));
  assert(p.accept({type:'assistant_playback_stop',seq:3,response_id:'r'}));
  assert(!p.accept({type:'dashboard_commit',seq:4,response_id:'r',batch_id:'b',dashboard_revision:1}));
  assert(!p.accept({type:'tool_result',seq:5,response_id:'r',batch_id:'b',call_id:'c'}));
});

test('commit and card replay only apply once', () => {
  const p = new SessionProjection();
  p.accept({type:'assistant_response_started',seq:1,response_id:'r'});
  p.accept({type:'tool_execution_started',seq:2,response_id:'r',batch_id:'b'});
  assert(p.accept({type:'dashboard_commit',seq:3,response_id:'r',batch_id:'b',dashboard_revision:1}));
  assert(!p.accept({type:'dashboard_commit',seq:4,response_id:'r',batch_id:'b',dashboard_revision:1}));
  assert(p.accept({type:'tool_call',seq:5,response_id:'r',batch_id:'b',call_id:'c'}));
  assert(!p.accept({type:'tool_call',seq:6,response_id:'r',batch_id:'b',call_id:'c'}));
});

test('revision immediately revokes old content but admits semantic terminal messages once', () => {
  const p = new SessionProjection();
  assert(p.accept({type:'assistant_response_started',seq:1,response_id:'old'}));
  assert(p.accept({type:'tool_execution_started',seq:2,response_id:'old',batch_id:'old-batch'}));
  assert(p.accept({type:'revision_received',seq:3,request_id:'new-request',previous_request_id:'old-request',previous_response_id:'old',revision_index:1,previous_phase:'reasoning',utterance_id:'u-new'}));
  assert(!p.accept({type:'revision_received',seq:3,request_id:'new-request',previous_request_id:'old-request',previous_response_id:'old',revision_index:1,previous_phase:'reasoning',utterance_id:'u-new'}));
  assert(!p.accept({type:'revision_received',seq:2,request_id:'reordered-request',previous_request_id:'old-request',previous_response_id:'old',revision_index:1,previous_phase:'reasoning',utterance_id:'u-old'}));
  assert(!p.accept({type:'transcript',seq:4,response_id:'old',role:'assistant',delta:'late'}));
  assert(!p.accept({type:'audio',seq:5,response_id:'old',data:'late'}));
  assert(!p.accept({type:'tool_call',seq:6,response_id:'old',batch_id:'old-batch',call_id:'c'}));
  assert(!p.accept({type:'tool_result',seq:7,response_id:'old',batch_id:'old-batch',call_id:'c'}));
  assert(!p.accept({type:'dashboard_commit',seq:8,response_id:'old',batch_id:'old-batch',dashboard_revision:1}));
  assert(p.accept({type:'response_superseded',seq:9,request_id:'old-request',response_id:'old',superseding_request_id:'new-request',previous_phase:'reasoning'}));
  assert(!p.accept({type:'response_superseded',seq:9,request_id:'old-request',response_id:'old',superseding_request_id:'new-request',previous_phase:'reasoning'}));
  assert(p.accept({type:'tool_execution_finished',seq:10,status:'superseded',response_id:'old',batch_id:'old-batch'}));
  assert(!p.accept({type:'tool_execution_finished',seq:11,status:'superseded',response_id:'old',batch_id:'old-batch'}));
  assert(!p.accept({type:'tool_execution_finished',seq:12,status:'succeeded',response_id:'old',batch_id:'old-batch'}));
});

test('superseded batch terminal is allowed only for its known batch', () => {
  const p = new SessionProjection();
  p.accept({type:'assistant_response_started',seq:1,response_id:'old'});
  p.accept({type:'tool_execution_started',seq:2,response_id:'old',batch_id:'known'});
  p.accept({type:'revision_received',seq:3,request_id:'new-request',previous_request_id:'old-request',previous_response_id:'old',revision_index:1,previous_phase:'tool_execution',utterance_id:'u-new'});
  assert(!p.accept({type:'tool_execution_finished',seq:4,status:'superseded',response_id:'old',batch_id:'unknown'}));
});

test('malformed revision does not consume dedupe identity or leave old response unrevoked', () => {
  const p = new SessionProjection();
  assert(p.accept({type:'assistant_response_started',seq:1,response_id:'old'}));
  assert(!p.accept({type:'revision_received',seq:2,request_id:'new-request'}));
  assert.equal(p.seq, 1);
  assert(p.accept({type:'revision_received',seq:2,request_id:'new-request',previous_request_id:'old-request',previous_response_id:'old',revision_index:1,previous_phase:'reasoning',utterance_id:'u-new'}));
  assert(!p.accept({type:'transcript',seq:3,response_id:'old',role:'assistant',delta:'late'}));
});

test('response supersession requires a valid superseding request before dedupe or revocation', () => {
  const p = new SessionProjection();
  assert(p.accept({type:'assistant_response_started',seq:1,response_id:'old'}));
  assert(!p.accept({type:'response_superseded',seq:2,request_id:'old-request',response_id:'old',previous_phase:'reasoning'}));
  assert.equal(p.seq, 1);
  assert(p.accept({type:'response_superseded',seq:2,request_id:'old-request',response_id:'old',superseding_request_id:'new-request',previous_phase:'reasoning'}));
  assert(!p.accept({type:'transcript',seq:3,response_id:'old',role:'assistant',delta:'late'}));
});
