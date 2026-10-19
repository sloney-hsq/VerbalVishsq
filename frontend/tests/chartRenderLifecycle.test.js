import test from 'node:test';
import assert from 'node:assert/strict';

import { createChartRenderLifecycle } from '../src/chartRenderLifecycle.js';

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

const meta = {
  renderToken: 'render-1', dashboardRevision: 4,
  viewId: 'view-a', viewRevision: 2,
  presentation: { mode: 'paged', page_index: 3 },
};

test('runAsync completion is required before a rendered acknowledgement', async () => {
  const emitted = [];
  const lifecycle = createChartRenderLifecycle((type, payload) => emitted.push({ type, payload }), () => 110);
  const gate = deferred();
  const ticket = lifecycle.start(meta, 100);
  const completion = lifecycle.complete(ticket, { runAsync: () => gate.promise });

  await Promise.resolve();
  assert.deepEqual(emitted, []);
  gate.resolve();
  await completion;
  assert.equal(emitted[0].type, 'rendered');
  assert.equal(emitted[0].payload.browser_duration_ms, 10);
  assert.deepEqual(emitted[0].payload.presentation, { mode: 'paged', page_index: 3 });
});

test('a stale generation and an unmounted chart never report completion', async () => {
  const emitted = [];
  const lifecycle = createChartRenderLifecycle((type, payload) => emitted.push({ type, payload }));
  const stale = lifecycle.start(meta);
  lifecycle.start({ ...meta, renderToken: 'render-2' });
  await lifecycle.complete(stale, { runAsync: async () => undefined });
  const unmounted = lifecycle.start({ ...meta, renderToken: 'render-3' });
  lifecycle.dispose();
  await lifecycle.complete(unmounted, { runAsync: async () => undefined });
  assert.deepEqual(emitted, []);
});

test('a presentation change invalidates the running page before its replacement starts', async () => {
  const emitted = [];
  const lifecycle = createChartRenderLifecycle((type, payload) => emitted.push({ type, payload }));
  const gate = deferred();
  const oldPage = lifecycle.start(meta);
  const completion = lifecycle.complete(oldPage, { runAsync: () => gate.promise });

  lifecycle.invalidate();
  gate.resolve();
  await completion;

  assert.deepEqual(emitted, []);
});

test('render failure emits only a whitelisted error code and render metadata', () => {
  const emitted = [];
  const lifecycle = createChartRenderLifecycle((type, payload) => emitted.push({ type, payload }));
  const ticket = lifecycle.start(meta);
  lifecycle.fail(ticket, 'run_async_failed', new Error('private data must not cross the wire'));

  assert.equal(emitted[0].type, 'render-failed');
  assert.equal(emitted[0].payload.error_code, 'run_async_failed');
  assert.equal(JSON.stringify(emitted[0]).includes('private data'), false);
});
