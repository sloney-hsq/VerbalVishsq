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

test('spoken view number precedes the title and has an accessible name', async t => {
  const vite = await createServer({server:{middlewareMode:true},appType:'custom',logLevel:'silent'});
  t.after(() => vite.close());
  const {default:ChartSlot} = await vite.ssrLoadModule('/src/components/ChartSlot.vue');
  const app = createSSRApp({render:() => h(ChartSlot,{displayNumber:3,
    view:{id:'id-unrelated-to-number',title:'Delivery times',chart_type:'bar',data:[]}})});
  app.use(createPinia());
  const html = await renderToString(app);
  assert.match(html,/aria-label="View 3"[^>]*>3<\/span>[\s\S]*?<h2[^>]*>Delivery times/);
});

test('chart spec validation is inside the visible render error boundary', async () => {
  const source = await readFile(fileURLToPath(new URL('../src/components/ChartSlot.vue', import.meta.url)), 'utf8');
  assert.match(source, /try\s*\{\s*const spec = createSpec\([\s\S]*?catch\s*\(error\)/);
  assert.match(source, /:deep\(svg\)[\s\S]*?max-width:\s*none/);
});

test('high-cardinality heatmaps expose accessible paging without mutating the view', async (t) => {
  const vite = await createServer({server:{middlewareMode:true},appType:'custom',logLevel:'silent'});
  t.after(() => vite.close());
  const {default:ChartSlot} = await vite.ssrLoadModule('/src/components/ChartSlot.vue');
  const data = Array.from({length:30},(_,i) => ({state:'SP',category:`C${i}`,score:i}));
  const view = {id:'heat',title:'Heat',chart_type:'heatmap',result_kind:'aggregate',data,
    visual:{type:'heatmap',encoding:{x:'state',y:'category',color:'score'}},
    columns:{state:{type:'nominal'},category:{type:'nominal'},score:{type:'quantitative'}}};
  const app = createSSRApp({render:() => h(ChartSlot,{view,availableWidth:920})});
  app.use(createPinia());
  const html = await renderToString(app);
  assert.match(html,/aria-label="Heatmap pages"/);
  assert.match(html,/1–20 of 30 categories/);
  assert.match(html,/Show all categories/);
  assert.equal(view.data.length,30);
});

test('independent facet scales are disclosed in card metadata', async (t) => {
  const vite = await createServer({server:{middlewareMode:true},appType:'custom',logLevel:'silent'});
  t.after(() => vite.close());
  const {default:ChartSlot} = await vite.ssrLoadModule('/src/components/ChartSlot.vue');
  const view = {id:'facet',title:'Facet',chart_type:'bar',data:[],
    visual:{type:'bar',encoding:{x:'group',y:'score',facet:'panel'},scales:{resolve:'independent'}},
    columns:{group:{type:'nominal'},score:{type:'quantitative'},panel:{type:'nominal'}}};
  const app = createSSRApp({render:() => h(ChartSlot,{view,availableWidth:920})});
  app.use(createPinia());
  assert.match(await renderToString(app),/Independent scales/);
});

test('analysis warnings and suppressed comparisons are expandable', async (t) => {
  const vite = await createServer({server:{middlewareMode:true},appType:'custom',logLevel:'silent'});
  t.after(() => vite.close());
  const {default:ChartSlot} = await vite.ssrLoadModule('/src/components/ChartSlot.vue');
  const view = {id:'period',title:'Period',chart_type:'line',data:[],
    visual:{type:'line',encoding:{x:'bucket',y:'score'}},columns:{bucket:{type:'quantitative'},score:{type:'quantitative'}},
    metadata:{warnings:['Outside observed range'],comparison_suppressed_reasons:'outside_observed_date_extent'}};
  const app = createSSRApp({render:() => h(ChartSlot,{view,availableWidth:920})});
  app.use(createPinia());
  const html = await renderToString(app);
  assert.match(html,/<details[^>]*class="analysis-notices"/);
  assert.match(html,/2 analysis notices/);
  assert.match(html,/Outside observed range/);
  assert.match(html,/Comparison suppressed: Outside observed date extent/);
});

test('compact card keeps routine context in a closed disclosure and paging actions accessible', async (t) => {
  const vite = await createServer({server:{middlewareMode:true},appType:'custom',logLevel:'silent'});
  t.after(() => vite.close());
  const {default:ChartSlot} = await vite.ssrLoadModule('/src/components/ChartSlot.vue');
  const data = Array.from({length:30},(_,i) => ({state:'SP',category:`C${i}`,score:i}));
  const view = {id:'heat',title:'Category performance',chart_type:'heatmap',result_kind:'aggregate',data,
    visual:{type:'heatmap',encoding:{x:'state',y:'category',color:'score'}},
    columns:{state:{type:'nominal'},category:{type:'nominal'},score:{type:'quantitative',label:'Performance',unit:'points'}},
    metadata:{observation_unit:'category-state result'}};
  const app = createSSRApp({render:() => h(ChartSlot,{view,availableWidth:3000})});
  app.use(createPinia());
  const html = await renderToString(app);

  assert.match(html,/class="chart-card__meta"/);
  assert.match(html,/Performance \(points\)/);
  assert.match(html,/30 result rows/);
  assert.match(html,/Observation unit: Category-state result/);
  assert.match(html,/Previous page/);
  assert.match(html,/Next page/);
  assert.match(html,/data-layout-span="1"/);
  assert.match(html,/data-chart-type="heatmap"/);
  assert.doesNotMatch(html.split('>')[0], /style="[^"]*grid-column/);
  assert.doesNotMatch(html,/Show all categories/);
  const disclosure = html.match(/<details[^>]*class="chart-card__info"[^>]*>[\s\S]*?<\/details>/)?.[0];
  assert.ok(disclosure, 'Routine metadata belongs in an information disclosure');
  assert.doesNotMatch(disclosure.split('>')[0], /\bopen\b/);
  assert.match(disclosure, /Performance \(points\)/);
  assert.match(disclosure, /Observation unit: Category-state result/);
  assert.match(disclosure, /aria-label="Chart details: Category performance"/);
  const outsideDisclosure = html.replace(disclosure, '');
  assert.doesNotMatch(outsideDisclosure, /30 result rows|Observation unit:|class="chart-type"/);
  assert.match(html, /aria-label="Previous page"/);
  assert.match(html, /aria-label="Next page"/);
});
