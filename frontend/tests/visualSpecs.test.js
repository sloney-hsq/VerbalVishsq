import test from 'node:test';
import assert from 'node:assert/strict';
import { compile } from 'vega-lite';
import * as vega from 'vega';
import { createSpec } from '../src/specFactory.js';

const cols = {
  cohort: {type:'nominal',label:'Cohort'}, period:{type:'temporal',label:'Period'},
  score:{type:'quantitative',label:'Score',unit:'points'}, weight:{type:'quantitative',label:'Weight',unit:'kg'},
  share:{type:'quantitative',label:'Share',unit:'ratio',already_normalized:true},
};
const view = (type, encoding, data, columns=cols, result_kind='aggregate', metadata={}) =>
  ({id:'v1',chart_type:type,visual:{type,encoding},result_kind,metadata,columns,data,title:type});

test('six typed chart families compile, and representative SVG renders', async () => {
  const examples = [
    view('bar',{x:'cohort',y:'score'},[{cohort:'A',score:4}]),
    view('line',{x:'period',y:'score'},[{period:'2026-01-01',score:4}]),
    view('scatter',{x:'weight',y:'score'},[{weight:2,score:4}]),
    view('heatmap',{x:'cohort',y:'period',color:'score'},[{cohort:'A',period:'2026-01-01',score:4}]),
    view('histogram',{x:'weight',y:'count'},[{bin_start:0,bin_end:2,count:4,proportion:1}],
      {bin_start:{type:'quantitative',unit:'kg'},bin_end:{type:'quantitative',unit:'kg'},count:{type:'quantitative',unit:'count'},proportion:{type:'quantitative',unit:'ratio'}},
      'histogram',{field:'weight'}),
    view('boxplot',{x:'cohort',y:'score'},[{cohort:'A',q1:2,median:3,q3:4,whisker_low:1,whisker_high:5}],
      {cohort:{type:'nominal'},q1:{type:'quantitative'},median:{type:'quantitative'},q3:{type:'quantitative'},whisker_low:{type:'quantitative'},whisker_high:{type:'quantitative'}},
      'box_summary',{field:'score'}),
  ];
  for (const example of examples) {
    const spec = createSpec(example);
    const compiled = compile({...spec,width:300,height:200}).spec;
    assert.ok(compiled.marks?.length, example.chart_type);
  }
  const svg = await new vega.View(vega.parse(compile({...createSpec(examples[4]),width:300,height:200}).spec),
    {renderer:'svg'}).toSVG();
  assert.match(svg, /<svg/);
});

test('box plot uses summary fields; histogram uses explicit bin endpoints', () => {
  const box = createSpec(view('boxplot',{x:'cohort',y:'score'},[{cohort:'A',q1:2,median:3,q3:4,whisker_low:1,whisker_high:5}],
    {cohort:{type:'nominal'},q1:{type:'quantitative'},median:{type:'quantitative'},q3:{type:'quantitative'},whisker_low:{type:'quantitative'},whisker_high:{type:'quantitative'}},'box_summary',{field:'score'}));
  assert.equal(box.layer.length, 3);
  assert.equal(box.layer[1].encoding.y.field, 'q3');
  assert.equal(box.layer[1].encoding.y2.field, 'q1');
  assert.equal(box.layer[2].encoding.y.field, 'median');
  const hist = createSpec(view('histogram',{x:'weight',y:'count'},[{bin_start:0,bin_end:2,count:4,proportion:1}],
    {bin_start:{type:'quantitative'},bin_end:{type:'quantitative'},count:{type:'quantitative'},proportion:{type:'quantitative'}},'histogram',{field:'weight'}));
  assert.equal(hist.encoding.x.field, 'bin_start');
  assert.equal(hist.encoding.x2.field, 'bin_end');
});

test('grouped bar stays side by side and share is not normalized twice', () => {
  const grouped = createSpec({...view('bar',{x:'cohort',y:'score',color:'period'},[{cohort:'A',period:'P1',score:2}],
    {...cols,period:{type:'nominal'}}),visual:{type:'bar',encoding:{x:'cohort',y:'score',color:'period'},stack:'none'}});
  assert.equal(grouped.encoding.xOffset.field, 'period');
  assert.equal(grouped.encoding.y.stack, null);
  const share = createSpec({...view('bar',{x:'cohort',y:'share',color:'period'},[{cohort:'A',period:'P1',share:0.5}],
    {...cols,period:{type:'nominal'}}),visual:{type:'bar',encoding:{x:'cohort',y:'share',color:'period'},stack:'zero'}});
  assert.equal(share.encoding.y.stack, 'zero');
  assert.equal(share.encoding.y.axis.format, '.1%');
});

test('boxplot accepts color and log scale without a missing encoding crash', () => {
  const box = createSpec({...view('boxplot',{x:'cohort',y:'score',color:'period'},
    [{cohort:'A',period:'P1',q1:2,median:3,q3:4,whisker_low:1,whisker_high:5}],
    {cohort:{type:'nominal'},period:{type:'nominal'},q1:{type:'quantitative'},median:{type:'quantitative'},q3:{type:'quantitative'},whisker_low:{type:'quantitative'},whisker_high:{type:'quantitative'}},
    'box_summary',{field:'score'}),visual:{type:'boxplot',encoding:{x:'cohort',y:'score',color:'period'},scales:{y:'log'}}});
  assert.equal(box.encoding.color.field, 'period');
  assert.equal(box.layer[0].encoding.y.scale.type, 'log');
  assert.ok(compile({...box,width:300,height:200}).spec.marks.length);
});

test('metric sort ranks bar categories on either axis', () => {
  const vertical = createSpec({...view('bar',{x:'cohort',y:'score'},[{cohort:'A',score:1},{cohort:'B',score:2}]),
    visual:{type:'bar',encoding:{x:'cohort',y:'score'},sort:{field:'score',direction:'desc'}}});
  assert.deepEqual(vertical.encoding.x.sort,{field:'score',op:'mean',order:'descending'});
  const horizontal = createSpec({...view('bar',{x:'score',y:'cohort'},[{cohort:'A',score:1},{cohort:'B',score:2}]),
    visual:{type:'bar',encoding:{x:'score',y:'cohort'},sort:{field:'score',direction:'asc'}}});
  assert.deepEqual(horizontal.encoding.y.sort,{field:'score',op:'mean',order:'ascending'});
});

test('ordinal order and palette are declared by metadata, not a domain name', () => {
  const custom = createSpec(view('bar',{x:'cohort',y:'score',color:'rating_band'},
    [{cohort:'A',score:1,rating_band:3},{cohort:'A',score:2,rating_band:1}],
    {...cols,rating_band:{type:'ordinal',sort_order:[1,2,3],color_range:['red','yellow','green']}}));
  assert.deepEqual(custom.encoding.color.scale.domain,[1,2,3]);
  assert.deepEqual(custom.encoding.color.scale.range,['red','yellow','green']);
  assert.deepEqual(custom.encoding.color.sort,[1,2,3]);
});

test('explicit selection highlight dims only nonmatching marks', () => {
  const target = {...view('bar',{x:'cohort',y:'score'},[{cohort:'A',score:1},{cohort:'B',score:2}]),
    selection_highlights:{source:[{field:'x',op:'eq',value:'A'}]}};
  const spec = createSpec(target);
  assert.deepEqual(spec.data.values.map(row => row.__selection_match),[true,false]);
  assert.equal(spec.encoding.opacity.value,0.22);
  assert.ok(compile({...spec,width:300,height:200}).spec.marks.length);
});
