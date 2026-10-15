import test from 'node:test';
import assert from 'node:assert/strict';
import { createSpec, formatFilter } from '../src/specFactory.js';

test('education temporal and metric labels come from interface metadata', () => {
  const spec = createSpec({chart_type:'line', x_field:'assessment_date', y_field:'mean_score', data:[],
    columns:{assessment_date:{type:'temporal',label:'Assessment date'}, mean_score:{type:'quantitative',label:'Mean score',unit:'points',description:'Average assessment score.'}}});
  assert.equal(spec.encoding.x.type, 'temporal');
  assert.equal(spec.encoding.y.title, 'Mean score (points)');
  assert.equal(spec.encoding.y.description, undefined);
  assert.equal(spec.usermeta.columns.mean_score.description, 'Average assessment score.');
  assert.match(spec.description, /Average assessment score\./);
  assert.equal(spec.encoding.tooltip[0].type, 'temporal');
});

test('quantitative color formatting uses a legend rather than an axis', () => {
  const spec = createSpec({chart_type:'scatter', x_field:'x', y_field:'y', color:'intensity', data:[],
    columns:{
      x:{type:'quantitative',label:'X',unit:'count'},
      y:{type:'quantitative',label:'Y',unit:'count'},
      intensity:{type:'quantitative',label:'Intensity',unit:'ratio'},
    }});
  assert.equal(spec.encoding.color.axis, undefined);
  assert.equal(spec.encoding.color.legend.format, '.1%');
});

test('quantitative formatting is selected from column units and preserves ratio values', () => {
  const cases = [
    {unit:'ratio', axis:'.1%', tooltip:'.1%'},
    {unit:'BRL', axis:',.2f', tooltip:',.2f'},
    {unit:'BRL/order', axis:',.2f', tooltip:',.2f'},
    {unit:'days', axis:',.2f', tooltip:',.2f'},
    {unit:'points', axis:',.2f', tooltip:',.2f'},
    {unit:'kg', axis:',.2f', tooltip:',.2f'},
    {unit:'orders', axis:',.0f', tooltip:',.0f'},
    {unit:'items', axis:',.0f', tooltip:',.0f'},
    {unit:'customers', axis:',.0f', tooltip:',.0f'},
    {unit:'count', axis:',.0f', tooltip:',.0f'},
    {unit:'cm3', axis:',.0f', tooltip:',.0f'},
  ];

  for (const {unit, axis, tooltip} of cases) {
    const spec = createSpec({
      chart_type:'bar', x_field:'segment', y_field:'metric', data:[{segment:'A',metric:0.125}],
      columns:{segment:{type:'nominal',label:'Segment'},metric:{type:'quantitative',label:'Metric',unit}},
    });
    assert.equal(spec.encoding.y.axis.format, axis, `${unit} axis format`);
    assert.equal(spec.encoding.tooltip[1].format, tooltip, `${unit} tooltip format`);
    assert.equal(spec.encoding.y.title, `Metric (${unit})`);
    assert.equal(spec.data.values[0].metric, 0.125, `${unit} keeps the numeric row value`);
  }
});

test('unknown chart columns fail visibly instead of guessing numerical types', () => {
  assert.throws(() => createSpec({chart_type:'bar', x_field:'missing', y_field:'score', columns:{}, data:[]}), /metadata/);
});

test('categorical series do not depend on commerce field names', () => {
  const spec = createSpec({chart_type:'bar',x_field:'cohort',y_field:'mean_score',color:'subject',data:[],
    columns:{cohort:{type:'nominal'},mean_score:{type:'quantitative'},subject:{type:'nominal'}}});
  assert.equal(spec.encoding.x.type, 'nominal');
  assert.equal(spec.encoding.color.field, 'subject');
});

test('filter chips use the interface field label and op contract', () => {
  const description = {resources:[{fields:{cohort:{type:'nominal',label:'Cohort'}}}]};
  assert.equal(formatFilter({field:'cohort',op:'eq',value:'A'},description), 'Cohort = A');
  assert.equal(formatFilter({field:'cohort',op:'is_null'},description), 'Cohort is missing');
});

test('filter chips resolve labels from dimension registries and display every operator', () => {
  const description = {
    dimension_index:{purchase_day:{type:'temporal',label:'Purchase day'}},
    dimensions:{people:[{field:'region',type:'nominal',label:'Region'}]},
    resources:[{fields:{cohort:{type:'nominal',label:'Cohort'}}}],
  };

  const cases = [
    [{field:'purchase_day',op:'gte',value:'2026-01-01'}, 'Purchase day ≥ 2026-01-01'],
    [{field:'purchase_day',op:'lte',value:'2026-12-31'}, 'Purchase day ≤ 2026-12-31'],
    [{field:'region',op:'neq',value:'North'}, 'Region ≠ North'],
    [{field:'region',op:'gt',value:10}, 'Region > 10'],
    [{field:'region',op:'lt',value:20}, 'Region < 20'],
    [{field:'region',op:'in',value:['North','South']}, 'Region in North, South'],
    [{field:'region',op:'between',value:[10,20]}, 'Region between 10 and 20'],
    [{field:'cohort',op:'eq',value:null}, 'Cohort = missing'],
    [{field:'cohort',op:'is_null'}, 'Cohort is missing'],
  ];

  for (const [filter, expected] of cases) {
    assert.equal(formatFilter(filter, description), expected);
  }
});
