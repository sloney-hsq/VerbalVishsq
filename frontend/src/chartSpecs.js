import { chartHeightForView } from './chartLayout.js';

const PALETTE = ['#2864b4','#c45325','#30846b','#8c51a5','#b78b1d','#4f7891','#b04973','#61773b','#885d46','#3b70c1'];

function encoding(view, field, channel='axis') {
  const metadata = view.columns?.[field];
  if (!metadata || !['nominal','ordinal','quantitative','temporal'].includes(metadata.type)) {
    throw new Error(`Missing or invalid column metadata: ${field}`);
  }
  const source = metadata.source_field || field;
  const readable = source.replaceAll('_',' ').replace(/^./,letter => letter.toUpperCase());
  const result = {field,type:metadata.type,title:`${metadata.label || readable}${metadata.unit ? ` (${metadata.unit})` : ''}`};
  const unit = String(metadata.unit || '').toLowerCase();
  const format = unit === 'ratio' ? '.1%' : unit === 'percentage_points' ? '+.1f' : unit === 'correlation' ? '.2f'
    : /\bbrl\b/.test(unit) || ['days','points','kg'].includes(unit) ? ',.2f'
    : ['count','orders','items','customers','observations','cm3'].includes(unit) ? ',.0f' : null;
  if (format && channel === 'axis') result.axis = {format};
  if (format && channel === 'tooltip') result.format = format;
  if (format && channel === 'legend') result.legend = {format};
  if (metadata.sort_order) result.sort = metadata.sort_order;
  return result;
}

function stableColor(view, field) {
  const values = [...new Set((view.data || []).map(row => row[field]).filter(value => value !== null && value !== undefined))]
    .sort((a,b) => String(a).localeCompare(String(b)));
  const declared = view.columns?.[field];
  if (declared?.sort_order && declared?.color_range) return {domain:declared.sort_order,range:declared.color_range};
  const hash = value => {let h=2166136261; for(const char of String(value)){h ^= char.codePointAt(0);h=Math.imul(h,16777619);} return (h>>>0)%PALETTE.length;};
  return {domain:values,range:values.map(value => PALETTE[hash(value)])};
}

function base(view, presentation = null) {
  const measure = ['color','y','x'].map(channel => view.visual?.encoding?.[channel])
    .find(field => view.columns?.[field]?.type === 'quantitative');
  const rows = presentation?.data || view.data || [];
  return {$schema:'https://vega.github.io/schema/vega-lite/v6.json',width:'container',height:presentation?.plotHeight || chartHeightForView(view),
    autosize:{type:'fit',contains:'padding',resize:true},data:{values:rows.map((row,index) => {
      const sourceIndex = Number.isInteger(row.__source_index) ? row.__source_index : index;
      return {...row,__row_order:sourceIndex,__valid_count:view.metadata?.row_valid_counts?.[sourceIndex]?.[measure]};
    })}};
}

function tooltip(view, fields) {
  const distinct = [...new Set([...fields, ...(view.visual?.encoding?.tooltip || []),
    ...(view.columns?.segment_denominator ? ['segment_denominator'] : [])].filter(field => field in (view.columns || {})))];
  const result = distinct.map(field => encoding(view,field,'tooltip'));
  if (view.metadata?.row_valid_counts) result.push({field:'__valid_count',type:'quantitative',title:'Valid observations',format:',.0f'});
  return result;
}

export function buildChartSpec(view, presentation = null) {
  const visual = view.visual;
  if (!visual || !visual.encoding) throw new Error('Typed visual is required');
  const {type} = visual;
  const {x,y,color,size,facet} = visual.encoding;
  let spec = base(view,presentation);
  const selections = Object.values(view.selection_highlights || {}).flat();
  if (selections.length) {
    spec.data.values = spec.data.values.map(row => ({...row,__selection_match:selections.every(item => {
      const field = visual.encoding[item.field] || item.field;
      const value = row[field], selected = item.value;
      return item.op === 'eq' ? value === selected : item.op === 'neq' ? value !== selected
        : item.op === 'gte' ? value >= selected : item.op === 'gt' ? value > selected
          : item.op === 'lte' ? value <= selected : item.op === 'lt' ? value < selected : false;
    })}));
  }
  const axis = field => encoding(view,field);
  const tool = (...fields) => tooltip(view,fields);
  if (type === 'bar') {
    const horizontal = view.columns?.[x]?.type === 'quantitative';
    spec.mark = {type:'bar',tooltip:true,cornerRadiusEnd:2};
    spec.encoding = {x:axis(x),y:axis(y),tooltip:tool(x,y,color)};
    const quantitative = horizontal ? spec.encoding.x : spec.encoding.y;
    quantitative.stack = visual.stack && visual.stack !== 'none' ? visual.stack : null;
    if (color && visual.stack !== 'zero' && visual.stack !== 'normalize') {
      spec.encoding[horizontal ? 'yOffset' : 'xOffset'] = {field:color,type:view.columns[color].type};
    }
  } else if (type === 'line') {
    spec.mark = {type:'line',point:true,tooltip:true};
    spec.encoding = {x:axis(x),y:axis(y),tooltip:tool(x,y,color)};
    spec.encoding.x.sort = 'ascending';
  } else if (type === 'scatter') {
    spec.mark = {type:'circle',tooltip:true,opacity:0.62};
    spec.encoding = {x:axis(x),y:axis(y),tooltip:tool(x,y,color,size)};
    if (size) spec.encoding.size = axis(size);
  } else if (type === 'heatmap') {
    spec.mark = {type:'rect',tooltip:true};
    spec.encoding = {x:axis(x),y:axis(y),color:encoding(view,color,'legend'),tooltip:tool(x,y,color)};
    if (view.columns?.[y]?.type !== 'quantitative') {
      spec.encoding.y.axis = {...spec.encoding.y.axis,labelLimit:220,labelFontSize:11};
      if (presentation?.visibleDomain) spec.encoding.y.sort = presentation.visibleDomain;
    }
    if (view.columns?.[color]?.type === 'quantitative') {
      spec.encoding.color.legend = {...spec.encoding.color.legend,orient:'top',direction:'horizontal',gradientLength:240,titleOrient:'left'};
      if (presentation?.colorDomain) spec.encoding.color.scale = {domain:presentation.colorDomain};
    }
    if (view.result_kind === 'binned_2d') {
      spec.encoding.x2 = {field:'x_bin_end'};
      spec.encoding.y2 = {field:'y_bin_end'};
    }
  } else if (type === 'histogram') {
    if (view.result_kind !== 'histogram') throw new Error('Histogram needs histogram result');
    spec.mark = {type:'bar',tooltip:true,orient:'vertical'};
    spec.encoding = {x:axis('bin_start'),x2:{field:'bin_end'},y:axis(y),tooltip:tool('bin_start','bin_end',y)};
    spec.encoding.x.bin = 'binned';
    spec.encoding.x.title = view.metadata?.field || spec.encoding.x.title;
  } else if (type === 'boxplot') {
    if (view.result_kind !== 'box_summary') throw new Error('Box plot needs box summary result');
    const group = x && view.columns?.[x] ? x : '__box__';
    if (group === '__box__') spec.data.values = spec.data.values.map(row => ({...row,__box__:'All'}));
    const xEncoding = group === '__box__' ? {field:group,type:'nominal',title:null} : axis(group);
    const yUnit = view.columns?.median?.unit;
    const yTitle = `${view.metadata?.field || 'Value'}${yUnit ? ` (${yUnit})` : ''}`;
    spec.layer = [
      {mark:{type:'rule',color:'#385c85'},encoding:{x:xEncoding,y:{field:'whisker_high',type:'quantitative',title:yTitle},y2:{field:'whisker_low'},tooltip:tool('whisker_low','q1','median','q3','whisker_high','valid_count','outlier_count')}},
      {mark:{type:'bar',size:22,color:'#7fa8d6'},encoding:{x:xEncoding,y:{field:'q3',type:'quantitative',title:yTitle},y2:{field:'q1'}}},
      {mark:{type:'tick',size:27,thickness:2,color:'#173b66'},encoding:{x:xEncoding,y:{field:'median',type:'quantitative',title:yTitle}}},
    ];
    spec.encoding = {};
  } else {
    throw new Error(`Unsupported chart type: ${type}`);
  }
  if (color && type !== 'heatmap') {
    spec.encoding.color = encoding(view,color,'legend');
    if (view.columns[color].type !== 'quantitative') spec.encoding.color.scale = stableColor(view,color);
  }
  const sort = visual.sort || view.source?.arguments?.sort;
  if (sort && spec.encoding) {
    const direction = sort.direction === 'asc' ? 'ascending' : 'descending';
    if (type === 'bar') {
      const category = view.columns?.[x]?.type === 'quantitative' ? 'y' : 'x';
      spec.encoding[category].sort = sort.field === spec.encoding[category].field ? direction
        : {field:sort.field,op:'mean',order:direction};
    } else if (type === 'boxplot') {
      spec.layer.forEach(layer => {if (layer.encoding.x) layer.encoding.x.sort = {field:sort.field,op:'mean',order:direction};});
    } else {
      const channel = Object.keys(spec.encoding).find(key => spec.encoding[key]?.field === sort.field);
      if (channel) spec.encoding[channel].sort = direction;
    }
  } else if (type === 'bar') {
    const category = view.columns?.[x]?.type === 'quantitative' ? 'y' : 'x';
    spec.encoding[category].sort = {field:'__row_order',op:'min',order:'ascending'};
  }
  if (visual.scales && spec.encoding) {
    for (const channel of ['x','y']) if (visual.scales[channel] === 'log' && spec.encoding[channel]) {
      spec.encoding[channel].scale = {type:'log'};
    }
    if (type === 'boxplot' && visual.scales.y === 'log') spec.layer.forEach(layer => {
      if (layer.encoding.y) layer.encoding.y.scale = {type:'log'};
    });
    if (visual.scales.resolve === 'independent') spec.resolve = {scale:{y:'independent'}};
  }
  if (selections.length) {
    if (type === 'boxplot') spec.layer.forEach(layer => {layer.encoding.opacity = {condition:{test:'datum.__selection_match',value:1},value:0.22};});
    else spec.encoding.opacity = {condition:{test:'datum.__selection_match',value:1},value:0.22};
  }
  if (facet) {
    const transformedData = spec.data;
    const facetSpec = {facet:encoding(view,facet),spec:{...spec}};
    delete facetSpec.spec.$schema;
    delete facetSpec.spec.data;
    delete facetSpec.spec.width;
    delete facetSpec.spec.height;
    delete facetSpec.spec.autosize;
    spec = {...base(view,presentation),data:transformedData,facet:facetSpec.facet,spec:facetSpec.spec};
    spec.autosize = {type:'pad',contains:'padding',resize:true};
    spec.columns = presentation?.facetColumns || 1;
    spec.spec.width = 260;
    spec.spec.height = 220;
    if (visual.scales?.resolve === 'independent') spec.resolve = {scale:{y:'independent'}};
  }
  spec.usermeta = {columns:view.columns,observation_unit:view.metadata?.observation_unit,
    effective_filters:view.metadata?.effective_filters,sampling:view.metadata?.sampling};
  return spec;
}
