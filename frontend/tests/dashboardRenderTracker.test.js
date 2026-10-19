import test from 'node:test';
import assert from 'node:assert/strict';

import { createDashboardRenderTracker } from '../src/dashboardRenderTracker.js';

function envelope(token='token-1', expectedViews=[{ view_id:'view-a', view_revision:2 }]) {
  return { token, dashboard_revision:4, expected_views:expectedViews, reason:'commit' };
}

test('an empty render set sends one explicit acknowledgement without waiting', () => {
  const sent = [];
  const tracker = createDashboardRenderTracker((type, payload) => sent.push({ type, payload }));
  tracker.activate(envelope('empty', []));
  assert.deepEqual(sent, [{
    type:'view.rendered',
    payload:{render_token:'empty',dashboard_revision:4,view_id:null,view_revision:null,
      render_generation:0,browser_duration_ms:0,presentation:{mode:'empty',page_index:null}},
  }]);
});

test('only current-token expected views are forwarded', () => {
  const sent = [];
  const tracker = createDashboardRenderTracker((type, payload) => sent.push({ type, payload }));
  tracker.activate(envelope('old'));
  tracker.activate(envelope('current'));

  assert.equal(tracker.forward('rendered', {render_token:'old',dashboard_revision:4,view_id:'view-a',view_revision:2,render_generation:1,browser_duration_ms:1,presentation:{mode:'paged',page_index:0}}), false);
  assert.equal(tracker.forward('rendered', {render_token:'current',dashboard_revision:4,view_id:'view-a',view_revision:9,render_generation:1,browser_duration_ms:1,presentation:{mode:'paged',page_index:0}}), false);
  assert.equal(tracker.forward('rendered', {render_token:'current',dashboard_revision:4,view_id:'view-a',view_revision:2,render_generation:2,browser_duration_ms:3,presentation:{mode:'paged',page_index:4}}), true);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].type, 'view.rendered');
  assert.deepEqual(sent[0].payload.presentation, {mode:'paged',page_index:4});
});
