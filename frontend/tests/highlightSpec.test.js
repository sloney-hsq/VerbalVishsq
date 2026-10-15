import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveHighlight } from '../src/highlightSpec.js';

const view = {
  chart_type:'line',
  x_field:'period',
  y_field:'amount',
  color:'group',
  columns:{
    period:{type:'temporal'},
    amount:{type:'quantitative'},
    group:{type:'nominal'},
    region:{type:'nominal'},
  },
  data:[
    {period:'2026-01',amount:10,group:'Alpha',region:'North'},
    {period:'2026-02',amount:20,group:'Beta',region:'South'},
  ],
};

test('generic x, series, and color aliases preserve structured highlight contracts', () => {
  assert.deepEqual(resolveHighlight(view, {field:'x',value:'2026-01'}).clauses, [
    {field:'period',value:'2026-01'},
  ]);
  assert.deepEqual(resolveHighlight(view, {field:'series',value:'Beta'}).clauses, [
    {field:'group',value:'Beta'},
  ]);
  assert.deepEqual(resolveHighlight(view, {x_value:'2026-02',series_value:'Beta'}).clauses, [
    {field:'period',value:'2026-02'},
    {field:'group',value:'Beta'},
  ]);
  assert.deepEqual(resolveHighlight(view, 'color=Alpha').clauses, [
    {field:'group',value:'Alpha'},
  ]);
});

test('highlight inference uses declared and actual result fields without domain aliases', () => {
  assert.deepEqual(resolveHighlight(view, 'North').clauses, [
    {field:'region',value:'North'},
  ]);

  const undeclared = {
    ...view,
    data:[{period:'2026-03',amount:30,group:'Gamma',channel:'Direct'}],
  };
  assert.deepEqual(resolveHighlight(undeclared, 'Direct').clauses, [
    {field:'channel',value:'Direct'},
  ]);
  assert.equal(resolveHighlight(view, 'week=2026-01'), null);
  assert.equal(resolveHighlight(view, 'state=North'), null);
});

test('structured clauses that never co-occur do not create a highlight badge', () => {
  assert.equal(resolveHighlight(view, {x_value:'2026-01',series_value:'Beta'}), null);
});
