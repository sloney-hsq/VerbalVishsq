import test from 'node:test';
import assert from 'node:assert/strict';
import { chartLayoutForView, heatmapPresentation } from '../src/chartLayout.js';
import * as chartLayout from '../src/chartLayout.js';

function heatmap(categoryCount = 72, states = ['RJ','SP']) {
  const data = [];
  for (let index = 0; index < categoryCount; index += 1) {
    for (const state of states) data.push({state, category:`Category ${index}`, score:index / 100});
  }
  return {
    id:'heat', chart_type:'heatmap', result_kind:'aggregate', data,
    visual:{type:'heatmap',encoding:{x:'state',y:'category',color:'score'}},
    columns:{state:{type:'nominal'},category:{type:'nominal'},score:{type:'quantitative',unit:'ratio'}},
    selection_highlights:{source:[{field:'category',op:'eq',value:'Category 40'}]},
  };
}

function simpleBar() {
  return {
    id:'bar', chart_type:'bar', data:[{group:'A',score:12}],
    visual:{type:'bar',encoding:{x:'group',y:'score'}},
    columns:{group:{type:'nominal',label:'Group'},score:{type:'quantitative',label:'Score',unit:'points'}},
  };
}

function rankedBar(count = 10) {
  return {
    id:'rank', chart_type:'bar',
    data:Array.from({length:count},(_,index) => ({category:`Long product category ${index}`,score:count - index})),
    visual:{type:'bar',encoding:{x:'category',y:'score'},sort:{field:'score',direction:'desc'}},
    columns:{category:{type:'nominal',label:'Product category'},score:{type:'quantitative',label:'Score'}},
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

test('4K cards gain plot and type scale without turning a heatmap into a full-width banner', () => {
  const wideChart = chartLayoutForView(simpleBar(),3200);
  const desktopChart = chartLayoutForView(simpleBar(),1400);
  const compactChart = chartLayoutForView(simpleBar(),950);
  const narrowHeatmap = chartLayoutForView(heatmap(),3200);
  const broadHeatmap = chartLayoutForView(heatmap(72,Array.from({length:8},(_,index) => `S${index}`)),3000);

  assert.equal(wideChart.columns,5);
  assert.equal(narrowHeatmap.columnSpan,1);
  assert.equal(narrowHeatmap.plotWidth,null);
  assert.equal(narrowHeatmap.plotMinWidth,0);
  assert.equal(broadHeatmap.columnSpan,1);
  assert.equal(broadHeatmap.plotWidth,null);
  assert.ok(wideChart.plotHeight >= 280);
  assert.ok(desktopChart.plotHeight > compactChart.plotHeight);
  assert.equal(wideChart.typography.axisLabel,14);
  assert.equal(desktopChart.typography.axisLabel,14);
  assert.equal(compactChart.typography.axisLabel,12);
  assert.ok(narrowHeatmap.plotHeight > 512);
});

test('five-column charts fit scaled 4K widths without forcing a horizontally scrollable heatmap', () => {
  const matrix = chartLayoutForView(heatmap(),1470);
  const chart = chartLayoutForView(simpleBar(),1470);
  assert.equal(matrix.columns,5);
  assert.equal(matrix.columnSpan,1);
  assert.equal(matrix.plotWidth,null);
  assert.equal(matrix.plotMinWidth,0);
  assert.ok(chart.plotHeight >= 200 && chart.plotHeight <= 220);
  assert.ok(chart.typography.axisLabel >= 12);
  const ranked = chartLayoutForView(rankedBar(),1470);
  assert.equal(ranked.categoryAxis.labelAngle,-55);
  assert.equal(ranked.categoryAxis.labelOverlap,false);
});

test('layout exposes responsive card bounds for paged and all-category views', () => {
  const wide = heatmapPresentation(heatmap(),{pageIndex:0,mode:'paged'},3000);
  const desktop = heatmapPresentation(heatmap(),{pageIndex:0,mode:'all'},1400);
  assert.equal(wide.bodyMaxHeight,760);
  assert.equal(desktop.bodyMaxHeight,640);
  assert.equal(wide.category.pageSize,20);
  assert.equal(desktop.data.length,144);
});

test('five-column canvas keeps category paging even if an earlier narrow layout requested all rows', () => {
  const view = heatmap();
  const first = heatmapPresentation(view,{pageIndex:0,mode:'all'},3000);
  const last = heatmapPresentation(view,{pageIndex:3,mode:'all'},3000);
  assert.equal(first.mode,'paged');
  assert.equal(first.scrollY,false);
  assert.equal(first.data.length,40);
  assert.equal(last.data.length,24);
  assert.deepEqual(last.colorDomain,first.colorDomain);
  assert.equal(view.data.length,144);
});

test('compact five-column heatmap pages leave room for the bottom conversation without dropping categories', () => {
  const source = heatmap();
  const first = heatmapPresentation(source,{pageIndex:0},1900);
  const last = heatmapPresentation(source,{pageIndex:5},1900);
  assert.equal(first.category.pageSize,12);
  assert.equal(first.pageCount,6);
  assert.equal(first.data.length,24);
  assert.equal(last.visibleDomain[0],'Category 60');
  assert.equal(last.data.length,24);
  assert.equal(first.plotHeight,348);
  assert.deepEqual(first.colorDomain,last.colorDomain);
  assert.deepEqual(Array.from({length:6},(_,pageIndex) => heatmapPresentation(source,{pageIndex},1900).visibleDomain).flat(),
    Array.from({length:72},(_,index) => `Category ${index}`));
  assert.equal(source.data.length,144);
});

test('dense categorical axes gain rotation and bottom budget without dropping labels', () => {
  const dense = chartLayoutForView(rankedBar(),1400);
  const sparse = chartLayoutForView(rankedBar(4),1400);
  assert.equal(dense.categoryAxis.labelAngle,-32);
  assert.equal(dense.categoryAxis.labelOverlap,false);
  assert.equal(dense.categoryAxis.labelLimit,130);
  assert.ok(dense.plotHeight > sparse.plotHeight);
  assert.equal(sparse.categoryAxis,null);
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

test('bounded cards use the actual plot budget and tall matrix keeps all categories reachable', () => {
  const bar = heatmapPresentation(simpleBar(),{},3800,780);
  assert.equal(bar.plotHeight,778);
  const first = heatmapPresentation(heatmap(),{},3800,900);
  assert.equal(first.plotHeight,898);
  assert.ok(first.category.pageSize > 20);
  assert.equal(first.category.enabled,true);
  const pages = Array.from({length:first.pageCount},(_,pageIndex) =>
    heatmapPresentation(heatmap(),{pageIndex},3800,900));
  assert.deepEqual(pages.flatMap(page => page.visibleDomain),Array.from({length:72},(_,i) => `Category ${i}`));
  assert.deepEqual(pages.at(-1).colorDomain,first.colorDomain);
  const tall = heatmapPresentation(heatmap(),{},3800,2050);
  assert.equal(tall.category.enabled,false);
  assert.equal(tall.data.length,144);
});

test('classic scrollbars cannot change the fixed plotting budget through content-box measurements', () => {
  const full = {borderBoxSize:[{inlineSize:360.97,blockSize:297.03}],contentRect:{width:360.97,height:297.03}};
  const bars = {...full,contentRect:{width:337.97,height:274.03}};
  assert.deepEqual(chartLayout.chartViewportForResize?.(full,true),{width:360,height:297});
  assert.deepEqual(chartLayout.chartViewportForResize?.(bars,true),{width:360,height:297});
  assert.deepEqual(chartLayout.chartViewportForResize?.(bars,false),{width:360,height:0});
});
