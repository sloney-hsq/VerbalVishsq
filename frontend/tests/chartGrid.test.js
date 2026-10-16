import test from 'node:test';
import assert from 'node:assert/strict';
import {packChartCards} from '../src/chartGrid.js';

test('natural-height cards fill the shorter column without stretching', () => {
  const positions = packChartCards([{height:600},{height:340},{height:300},{height:560}]);
  assert.deepEqual(positions.map(({column,row}) => [column,row]), [[1,1],[2,1],[2,357],[1,617]]);
});

test('wide charts clear both columns and narrow screens retain source order', () => {
  const cards = [{height:600},{height:340},{height:300,span:2},{height:200}];
  assert.deepEqual(packChartCards(cards)[2], {column:1,row:617,rowSpan:316,span:2});
  const narrow = packChartCards(cards,1);
  assert.deepEqual(narrow.map(card => card.column), [1,1,1,1]);
  assert.deepEqual(narrow.map(card => card.row), [1,617,973,1289]);
  assert.deepEqual(packChartCards([]), []);
});
