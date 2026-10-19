import test from 'node:test';
import assert from 'node:assert/strict';
import { createSSRApp, h } from 'vue';
import { createPinia } from 'pinia';
import { renderToString } from '@vue/server-renderer';
import { createServer } from 'vite';

function provideBrowserLocation(t) {
  const previous = globalThis.window;
  globalThis.window = { location: { search: '' } };
  t.after(() => { if (previous === undefined) delete globalThis.window; else globalThis.window = previous; });
}

test('workspace preserves full conversation, revision feedback and accessible analysis steps', async t => {
  provideBrowserLocation(t);
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  t.after(() => vite.close());
  const { default: Dashboard } = await vite.ssrLoadModule('/src/components/Dashboard.vue');
  const { useDashboardStore } = await vite.ssrLoadModule('/src/stores/dashboard.js');
  const pinia = createPinia();
  const store = useDashboardStore(pinia);
  const text = 'A long explanation remains readable. '.repeat(12);
  store.transcriptItems = [
    { id: 'u1', role: 'user', requestId: 'r1', text: 'Compare the two regions.', status: 'completed', startedAt: 1000, revisionAccepted: true },
    { id: 'a1', role: 'assistant', requestId: 'r1', responseId: 'response1', text, status: 'completed', startedAt: 2000 },
    { id: 't1', role: 'tool', requestId: 'r1', responseId: 'response1', toolName: 'aggregate', summary: 'Compare regions', status: 'completed', startedAt: 2500 },
  ];
  const app = createSSRApp({ render: () => h(Dashboard, { previewMode: true }) });
  app.use(pinia);
  const html = await renderToString(app);
  assert.ok(html.includes(text));
  assert.match(html, /aria-label="Session conversation"/);
  assert.match(html, /workspace--conversation-bottom/);
  assert.match(html, /aria-label="Hide conversation"/);
  assert.match(html, /Revision accepted/);
  assert.match(html, /1 analysis step/);
  assert.match(html, /Saved charts · voice offline/);
  assert.doesNotMatch(html, /Preview mode|Preview only|Layout preview|A place to explore ideas/);
  assert.match(html, /<h1\b[^>]*>VerbalVis<\/h1>/);
  assert.match(html, /<h2 class="workspace-view-count"[^>]*>0 views<\/h2>/);
  const toolbar = html.match(/<header class="workspace-topbar"[^>]*>[\s\S]*?<\/header>/)?.[0];
  assert.match(toolbar, /0 views/);
  assert.match(toolbar, /All data/);
  assert.doesNotMatch(html, /Conversational visual analytics|Saved results · layout preview|YOUR ANALYSIS|Explore the evidence/);
});

test('workspace shows configured connection errors without claiming a live session', async t => {
  provideBrowserLocation(t);
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  t.after(() => vite.close());
  const { default: Dashboard } = await vite.ssrLoadModule('/src/components/Dashboard.vue');
  const { useRuntimeStore } = await vite.ssrLoadModule('/src/stores/runtime.js');
  const pinia = createPinia();
  useRuntimeStore(pinia).setConfigurationError('Live service is unavailable.');
  const app = createSSRApp({ render: () => h(Dashboard) });
  app.use(pinia);
  const html = await renderToString(app);
  assert.match(html, /Live service is unavailable\./);
  assert.match(html, /role="status"/);
  assert.doesNotMatch(html, /Layout preview/);
});
