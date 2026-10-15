import test from 'node:test';
import assert from 'node:assert/strict';
import { createSSRApp, h } from 'vue';
import { createPinia } from 'pinia';
import { renderToString } from '@vue/server-renderer';
import { createServer } from 'vite';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

test('chart cards do not show a metric-specific low-score threshold badge', async (t) => {
  const vite = await createServer({server:{middlewareMode:true},appType:'custom',logLevel:'silent'});
  t.after(() => vite.close());
  const {default:ChartSlot} = await vite.ssrLoadModule('/src/components/ChartSlot.vue');
  const app = createSSRApp({
    render:() => h(ChartSlot, {view:{
      id:'view1', title:'Quality', chart_type:'bar', x_field:'group', y_field:'low_score_ratio',
      low_score_threshold:2, data:[], columns:{group:{type:'nominal'},low_score_ratio:{type:'quantitative'}},
    }}),
  });
  app.use(createPinia());

  const html = await renderToString(app);
  assert.doesNotMatch(html, /Low score|threshold/i);
});

test('chart spec validation is inside the visible render error boundary', async () => {
  const source = await readFile(fileURLToPath(new URL('../src/components/ChartSlot.vue', import.meta.url)), 'utf8');
  assert.match(source, /try\s*\{\s*const spec = createSpec\([\s\S]*?catch\s*\(error\)/);
});
