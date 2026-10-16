import test from 'node:test';
import assert from 'node:assert/strict';
import { compile } from 'vega-lite';
import * as vega from 'vega';
import { reactive } from 'vue';
import { createSpec } from '../src/specFactory.js';
import { heatmapPresentation } from '../src/chartLayout.js';

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
  assert.equal(hist.mark.orient, 'vertical');
  assert.equal(hist.encoding.x.bin, 'binned');
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

test('faceted highlight retains augmented rows and sample tooltip is visible', () => {
  const target = {...view('bar',{x:'cohort',y:'score',facet:'period'},
    [{cohort:'A',period:'P1',score:1},{cohort:'B',period:'P2',score:2}],
    {...cols,period:{type:'nominal'}},'aggregate',
    {row_valid_counts:[{score:3},{score:5}]}),
    selection_highlights:{source:[{field:'x',op:'eq',value:'A'}]}};
  const spec = createSpec(target);
  assert.deepEqual(spec.data.values.map(row => row.__selection_match),[true,false]);
  assert.deepEqual(spec.data.values.map(row => row.__valid_count),[3,5]);
  assert.ok(spec.spec.encoding.tooltip.some(item => item.field === '__valid_count'));
  assert.ok(compile({...spec,width:300,height:200}).spec.marks.length);
});

test('source sort and emitted row order survive without visual sort', () => {
  const ranked = {...view('bar',{x:'cohort',y:'score'},[{cohort:'B',score:2},{cohort:'A',score:1}]),
    source:{tool:'aggregate',arguments:{sort:{field:'score',direction:'desc'}}}};
  assert.deepEqual(createSpec(ranked).encoding.x.sort,{field:'score',op:'mean',order:'descending'});
  const returned = createSpec(view('bar',{x:'cohort',y:'score'},[{cohort:'B',score:2},{cohort:'A',score:1}]));
  assert.deepEqual(returned.encoding.x.sort,{field:'__row_order',op:'min',order:'ascending'});
});

test('paged heatmaps retain global scales, stable category order, and readable labels', () => {
  const rows = Array.from({length:70},(_,index) => ({group:`Category ${index}`,score:index}));
  const heat = view('heatmap',{x:'cohort',y:'group',color:'score'},rows,
    {...cols,group:{type:'nominal',source_field:'product_category'}});
  const presentation = heatmapPresentation(heat,{pageIndex:1,mode:'paged'},920);
  const spec = createSpec(heat,null,presentation);
  assert.equal(spec.height,512);
  assert.equal(spec.data.values.length,20);
  assert.deepEqual(spec.encoding.y.sort,presentation.visibleDomain);
  assert.deepEqual(spec.encoding.color.scale.domain,[0,69]);
  assert.equal(spec.encoding.color.legend.orient,'top');
  assert.equal(spec.encoding.y.title,'Product category');
  assert.equal(spec.encoding.y.axis.labelLimit,220);
  const points = createSpec(view('scatter',{x:'x_value',y:'y_value'},[{x_value:2,y_value:3}],
    {x_value:{type:'quantitative',source_field:'price',unit:'BRL'},
     y_value:{type:'quantitative',source_field:'freight_value',unit:'BRL'}},'points'));
  assert.equal(points.encoding.x.title,'Price (BRL)');
  assert.equal(points.encoding.y.title,'Freight value (BRL)');
});

test('percentage points and correlations have distinct numeric formats', () => {
  const percentagePoints = createSpec(view('bar',{x:'cohort',y:'delta'},[{cohort:'A',delta:5}],
    {cohort:{type:'nominal'},delta:{type:'quantitative',unit:'percentage_points'}}));
  const correlation = createSpec(view('bar',{x:'cohort',y:'rho'},[{cohort:'A',rho:.4567}],
    {cohort:{type:'nominal'},rho:{type:'quantitative',unit:'correlation'}},'relationship_summary'));
  assert.equal(percentagePoints.encoding.y.axis.format,'+.1f');
  assert.equal(correlation.encoding.y.axis.format,'.2f');
});

test('reactive column metadata is converted to a cloneable Vega spec', () => {
  const reactiveView = reactive(view('bar',{x:'cohort',y:'score',color:'band'},
    [{cohort:'A',score:1,band:'low'}],{...cols,band:{type:'ordinal',sort_order:['low','high'],color_range:['blue','red']}}));
  const spec = createSpec(reactiveView);
  assert.doesNotThrow(() => structuredClone(spec));
  assert.ok(compile(spec).spec.marks.length);
});

test('paged heatmap validity metadata follows source rows and the color measure', () => {
  const rows = Array.from({length:30},(_,index) => ({cohort:'A',group:`C${index}`,score:index}));
  const heat = view('heatmap',{x:'cohort',y:'group',color:'score'},rows,
    {...cols,group:{type:'nominal'}},'aggregate',{row_valid_counts:rows.map((_,index) => ({score:100 + index}))});
  const presentation = heatmapPresentation(heat,{pageIndex:1,mode:'paged'},920);
  const spec = createSpec(heat,null,presentation);
  assert.deepEqual(spec.data.values.map(row => row.__valid_count),Array.from({length:10},(_,index) => 120 + index));
  assert.ok(spec.encoding.tooltip.some(item => item.field === '__valid_count'));
});

test('facets use responsive columns and child dimensions without fit autosize', () => {
  const target = view('bar',{x:'cohort',y:'score',facet:'period'},
    [{cohort:'A',period:'P1',score:1}],{...cols,period:{type:'nominal'}});
  const wide = createSpec(target,null,{plotHeight:300,facetColumns:2});
  const narrow = createSpec(target,null,{plotHeight:300,facetColumns:1});
  assert.equal(wide.columns,2);
  assert.equal(narrow.columns,1);
  assert.equal(wide.autosize.type,'pad');
  assert.equal(Object.hasOwn(wide.spec,'autosize'),false);
});

test('period and quantile result tooltips include declared context fields', () => {
  const periods = view('line',{x:'bucket_index',y:'metric',color:'period'},
    [{bucket_index:0,metric:4,period:'Before',bucket_start:'2025-01-01',bucket_end:'2025-02-01',bucket_present:true,record_count:12}],
    {bucket_index:{type:'quantitative'},metric:{type:'quantitative'},period:{type:'nominal'},bucket_start:{type:'temporal'},bucket_end:{type:'temporal'},bucket_present:{type:'nominal'},record_count:{type:'quantitative',unit:'count'}},'periods');
  assert.deepEqual(createSpec(periods).encoding.tooltip.map(item => item.field),
    ['bucket_index','metric','period','bucket_start','bucket_end','bucket_present','record_count']);
  const quantiles = view('line',{x:'quantile',y:'value'},[{quantile:.9,value:4,valid_count:12,missing_count:2}],
    {quantile:{type:'quantitative'},value:{type:'quantitative'},valid_count:{type:'quantitative',unit:'count'},missing_count:{type:'quantitative',unit:'count'}},'quantiles');
  assert.deepEqual(createSpec(quantiles).encoding.tooltip.map(item => item.field),
    ['quantile','value','valid_count','missing_count']);
});
