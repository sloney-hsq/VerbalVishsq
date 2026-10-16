import test from 'node:test';
import assert from 'node:assert/strict';
import { chartLayoutForView, heatmapPresentation } from '../src/chartLayout.js';

function heatmap(categoryCount = 72) {
  const data = [];
  for (let index = 0; index < categoryCount; index += 1) {
    for (const state of ['RJ', 'SP']) data.push({state, category:`Category ${index}`, score:index / 100});
  }
  return {
    id:'heat', chart_type:'heatmap', result_kind:'aggregate', data,
    visual:{type:'heatmap',encoding:{x:'state',y:'category',color:'score'}},
    columns:{state:{type:'nominal'},category:{type:'nominal'},score:{type:'quantitative',unit:'ratio'}},
    selection_highlights:{source:[{field:'category',op:'eq',value:'Category 40'}]},
  };
}

test('high-cardinality Y heatmaps page complete categories in source order', () => {
  const view = heatmap();
  const layout = chartLayoutForView(view, 920);
  assert.equal(layout.columnSpan, 2);
  assert.equal(layout.heatmap.pageCount, 4);
  const first = heatmapPresentation(view,{pageIndex:0,mode:'paged'},920);
  const last = heatmapPresentation(view,{pageIndex:3,mode:'paged'},920);
  assert.deepEqual(first.visibleDomain, Array.from({length:20},(_,i) => `Category ${i}`));
  assert.equal(first.data.length, 40);
  assert.equal(last.visibleDomain.length, 12);
  assert.equal(last.data.length, 24);
  assert.deepEqual(first.colorDomain,[0,0.71]);
  assert.equal(first.selectionOffPage,true);
  assert.equal(last.selectionOffPage,true);
});

test('24 categories do not page and binned heatmaps never page', () => {
  assert.equal(chartLayoutForView(heatmap(24),920).heatmap.enabled,false);
  const binned = {...heatmap(30),result_kind:'binned_2d',columns:{x:{type:'quantitative'},y:{type:'quantitative'},score:{type:'quantitative'}},visual:{type:'heatmap',encoding:{x:'x',y:'y',color:'score'}}};
  assert.equal(chartLayoutForView(binned,920).heatmap.enabled,false);
});

test('all mode retains every row and narrow layouts use one dashboard column', () => {
  const view = heatmap();
  const all = heatmapPresentation(view,{pageIndex:2,mode:'all'},700);
  assert.equal(all.data.length,144);
  assert.equal(all.visibleDomain.length,72);
  assert.equal(all.pageIndex,2);
  assert.equal(chartLayoutForView(view,879).columnSpan,1);
  assert.doesNotThrow(() => heatmapPresentation({...view,data:[]},{pageIndex:99,mode:'paged'},920));
});

test('facets wrap two columns on wide containers and one on narrow containers', () => {
  const view = heatmap(2);
  view.chart_type = 'bar';
  view.visual = {type:'bar',encoding:{x:'state',y:'score',facet:'category'}};
  assert.equal(chartLayoutForView(view,920).facetColumns,2);
  assert.equal(chartLayoutForView(view,879).facetColumns,1);
});

test('long horizontal bars preserve readable rows inside a tall scroll tier', () => {
  const data = Array.from({length:55},(_,index) => ({category:`Category ${index}`,score:index}));
  const view = {chart_type:'bar',data,visual:{type:'bar',encoding:{x:'score',y:'category'}},
    columns:{score:{type:'quantitative'},category:{type:'nominal'}}};
  const layout = chartLayoutForView(view,920);
  assert.equal(layout.tier,'tall');
  assert.equal(layout.scrollY,true);
  assert.equal(layout.plotHeight,1052);
  assert.equal(layout.cardHeight,600);
  const first = heatmapPresentation(view,{pageIndex:0},920);
  const last = heatmapPresentation(view,{pageIndex:3},920);
  assert.equal(first.data.length,14);
  assert.equal(first.plotHeight,328);
  assert.equal(first.scrollY,false);
  assert.deepEqual(first.valueDomain,[0,54]);
  assert.deepEqual(last.valueDomain,first.valueDomain);
  assert.equal(last.data.length,13);
  assert.equal(last.data[0].category,'Category 42');
  const full = heatmapPresentation(view,{mode:'all'},920);
  assert.equal(full.data.length,55);
  assert.equal(full.scrollY,true);
  assert.equal(view.data.length,55);
});
