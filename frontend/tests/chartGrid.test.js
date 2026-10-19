import test from 'node:test';
import assert from 'node:assert/strict';
import {chartColumnCount,packChartCards} from '../src/chartGrid.js';
import * as chartGrid from '../src/chartGrid.js';

test('desktop grid uses the available 16:9 workspace instead of a fixed two-column limit', () => {
  assert.equal(chartColumnCount(3000),5);
  assert.equal(chartColumnCount(1920 - 48),5);
  assert.equal(chartColumnCount(1470),5);
  assert.equal(chartColumnCount(1366 - 48),2);
  assert.equal(chartColumnCount(879),1);
});

test('five-column workspace reserves the rightmost lane for heatmaps without changing source order', () => {
  const cards = [
    {height:300,chartType:'bar'}, {height:800,chartType:'heatmap'},
    {height:200,chartType:'line'}, {height:400,chartType:'scatter'},
    {height:120,chartType:'heatmap'}, {height:200,chartType:'bar'},
  ];
  const original = structuredClone(cards);
  const positions = packChartCards(cards,5);
  assert.deepEqual(positions.map(({column,row}) => [column,row]),
    [[1,1],[5,1],[2,1],[3,1],[5,817],[4,1]]);
  assert.deepEqual(cards,original);
});

test('ordinary spans stay outside the heatmap lane and a heatmap never spans into ordinary cards', () => {
  const positions = packChartCards([
    {height:120,chartType:'bar'}, {height:260,chartType:'bar',span:2},
    {height:500,chartType:'heatmap',span:2}, {height:300,chartType:'line'},
  ],5);
  assert.deepEqual(positions.map(({column,span,row}) => [column,span,row]),
    [[1,1,1],[2,2,1],[5,1,1],[4,1,1]]);
});

test('without heatmaps all five columns remain usable; narrow screens keep normal packing', () => {
  assert.deepEqual(packChartCards(Array.from({length:5},() => ({height:200,chartType:'bar'})),5)
    .map(card => card.column),[1,2,3,4,5]);
  const cards = [{height:200,chartType:'heatmap'}, {height:200,chartType:'bar'}, {height:100,chartType:'line'}];
  assert.deepEqual(packChartCards(cards,2).map(card => card.column),[1,2,1]);
  assert.deepEqual(packChartCards(cards,1).map(card => card.row),[1,217,433]);
});

test('natural-height cards fill the shorter column without stretching', () => {
  const positions = packChartCards([{height:600},{height:340},{height:300},{height:560}]);
  assert.deepEqual(positions.map(({column,row}) => [column,row]), [[1,1],[2,1],[2,357],[1,617]]);
});

test('canvas fit is determined from every packed column, including the tall heatmap lane', () => {
  const positions = packChartCards([
    {height:300,chartType:'bar'}, {height:800,chartType:'heatmap'},
    {height:200,chartType:'line'}, {height:120,chartType:'heatmap'},
  ],5);
  assert.equal(chartGrid.packedContentHeight?.(positions),952);
  assert.equal(chartGrid.packedContentHeight?.([]),0);
});

test('wide charts clear both columns and narrow screens retain source order', () => {
  const cards = [{height:600},{height:340},{height:300,span:2},{height:200}];
  assert.deepEqual(packChartCards(cards)[2], {column:1,row:617,rowSpan:316,span:2});
  const narrow = packChartCards(cards,1);
  assert.deepEqual(narrow.map(card => card.column), [1,1,1,1]);
  assert.deepEqual(narrow.map(card => card.row), [1,617,973,1289]);
  assert.deepEqual(packChartCards([]), []);
});

test('nine-view desktop places binned heatmap in the equal 2 by 4 grid and one category matrix across both rows', () => {
  const cards = Array.from({length:9},(_,index) => ({height:200 + index * 35,chartType:'bar'}));
  cards[3].chartType = 'heatmap';
  cards[8] = {height:360,chartType:'heatmap',resultKind:'binned_2d'};
  const original = structuredClone(cards);
  const positions = packChartCards(cards,5,20,1000);
  assert.deepEqual(positions.map(({column,row,height}) => [column,row,height]),[
    [1,1,490],[2,1,490],[3,1,490],[5,1,1000],[4,1,490],
    [1,511,490],[2,511,490],[3,511,490],[4,511,490],
  ]);
  assert.equal(chartGrid.packedContentHeight(positions),1000);
  assert.deepEqual(cards,original);
});

test('fixed grid never drops overflow cards or forces facets into a narrow cell', () => {
  const cards = Array.from({length:10},() => ({height:300,chartType:'bar'}));
  cards[0].chartType = 'heatmap';
  assert.equal(packChartCards(cards,5,20,1000).length,10);
  assert.equal(packChartCards(cards,5,20,1000)[0].height,undefined);
  cards.pop();
  cards[1].span = 2;
  assert.equal(packChartCards(cards,5,20,1000)[0].height,undefined);
});

test('fractional desktop spacing still produces valid integer CSS grid lines without overlap', () => {
  const cards = Array.from({length:9},(_,i) => ({height:300,chartType:i === 3 ? 'heatmap' : 'bar'}));
  const positions = packChartCards(cards,5,27.65,1964);
  assert.equal(positions[5].row,997);
  assert.equal(positions[3].rowSpan,1964);
  assert.ok(positions.every(p => Number.isInteger(p.row) && Number.isInteger(p.rowSpan)));
});

test('spoken view numbers follow left cards first then the right matrix, not the raw source index', () => {
  const views = [{id:'a',chart_type:'bar'},{id:'matrix',chart_type:'heatmap'},
    {id:'bins',chart_type:'heatmap',result_kind:'binned_2d'},{id:'b',chart_type:'line'}];
  assert.deepEqual(chartGrid.chartDisplayNumbers?.(views),{a:1,bins:2,b:3,matrix:4});
  assert.deepEqual(chartGrid.chartDisplayNumbers?.(views.filter(v => v.id !== 'bins')),{a:1,b:2,matrix:3});
});
