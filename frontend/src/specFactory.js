import { applyHighlightToSpec } from './highlightSpec.js';
import { chartHeightForView } from './chartLayout.js';
import { buildChartSpec } from './chartSpecs.js';

export function formatFilter(filter, description = {}) {
  if (filter?.op === 'or' && Array.isArray(filter.branches)) {
    return filter.branches.map(branch => {
      const leaves = Array.isArray(branch?.all) ? branch.all : [];
      return `(${leaves.map(leaf => formatFilter(leaf,description)).join(' and ')})`;
    }).join(' or ');
  }
  const metadata = filterMetadata(description, filter.field);
  const label = metadata?.label || filter.field;
  const op = filter.op;
  if (op === 'is_null') return `${label} is missing`;
  if (op === 'in') return `${label} in ${formatList(filter.value)}`;
  if (op === 'between') {
    const [start, end] = Array.isArray(filter.value) ? filter.value : [filter.value, undefined];
    return `${label} between ${formatValue(start)} and ${formatValue(end)}`;
  }
  if (op === 'quantile_between') {
    const lower = Number.isFinite(filter.value?.lower) ? `${formatPercent(filter.value.lower)}–` : '≤';
    const upper = Number.isFinite(filter.value?.upper) ? formatPercent(filter.value.upper) : 'maximum';
    return `${label} quantile ${lower}${upper}`;
  }
  const operators = {eq:'=', neq:'≠', gte:'≥', lte:'≤', gt:'>', lt:'<'};
  return `${label} ${operators[op] || op} ${formatValue(filter.value)}`;
}

function formatPercent(value) {
  return `${Number((value * 100).toFixed(2))}%`;
}

/** Encodings follow the interface result, never a hard-coded domain field list. */
export function createSpec(view, highlightElement = null, presentation = null) {
  const sourceView = toPlainData(view);
  const sourceHighlight = toPlainData(highlightElement);
  if (sourceView.visual) {
    const spec = buildChartSpec(sourceView,presentation);
    return ['bar','line','scatter'].includes(sourceView.visual.type)
      ? applyHighlightToSpec(spec, sourceView, sourceHighlight) : spec;
  }
  const encoding = (field, channel = 'axis') => {
    const metadata = sourceView.columns?.[field];
    if (!metadata || !['nominal', 'ordinal', 'quantitative', 'temporal'].includes(metadata.type)) {
      throw new Error(`Missing or invalid column metadata: ${field}`);
    }
    const result = {
      field,
      type: metadata.type,
      title: `${metadata.label || field}${metadata.unit ? ` (${metadata.unit})` : ''}`,
    };
    const format = metadata.type === 'quantitative' ? formatForUnit(metadata.unit) : null;
    if (format && channel === 'tooltip') result.format = format;
    if (format && channel === 'axis') result.axis = {format};
    if (format && channel === 'legend') result.legend = {format};
    return result;
  };
  if (!['bar', 'line', 'scatter'].includes(sourceView.chart_type)) throw new Error('Unsupported chart type');
  const x = encoding(sourceView.x_field), y = encoding(sourceView.y_field);
  const tooltip = [encoding(sourceView.x_field, 'tooltip'), encoding(sourceView.y_field, 'tooltip')];
  const spec = {
    $schema: 'https://vega.github.io/schema/vega-lite/v6.json',
    width: presentation?.fitWidth ?? 'container', height: presentation?.plotHeight || chartHeightForView(view),
    autosize: {type: 'fit', contains: 'padding', resize: true},
    padding: {left:4,right:8,top:6,bottom:4},
    config: responsiveConfig(presentation),
    data: {values: (sourceView.data || []).map(row => ({...row}))},
    mark: sourceView.chart_type === 'scatter' ? {type:'circle', tooltip:true, opacity:0.62}
      : sourceView.chart_type === 'line' ? {type:'line', point:true, tooltip:true}
        : {type:'bar', tooltip:true, cornerRadiusEnd:2},
    encoding: {x, y, tooltip},
  };
  const describedFields = [...new Set([sourceView.x_field, sourceView.y_field, sourceView.color].filter(Boolean))];
  spec.usermeta = {
    columns: Object.fromEntries(describedFields.map(field => [field, {...sourceView.columns[field]}])),
  };
  const descriptions = describedFields
    .map(field => sourceView.columns[field]?.description)
    .filter(Boolean);
  if (descriptions.length) spec.description = descriptions.join(' ');
  if (sourceView.chart_type === 'line') x.sort = 'ascending';
  if (sourceView.chart_type === 'bar' && x.type === 'nominal') {
    x.sort = '-y';
    if (presentation?.categoryAxis) x.axis = {...x.axis,...presentation.categoryAxis};
  }
  if (sourceView.color) {
    spec.encoding.color = encoding(sourceView.color, 'legend');
    tooltip.push(encoding(sourceView.color, 'tooltip'));
    if (sourceView.chart_type === 'line') spec.encoding.detail = {field:sourceView.color};
  }
  return applyHighlightToSpec(spec, sourceView, sourceHighlight);
}

function toPlainData(value) {
  if (value === null || value === undefined) return value;
  return JSON.parse(JSON.stringify(value));
}

function formatForUnit(unit) {
  const normalized = String(unit || '').trim().toLowerCase();
  if (normalized === 'ratio') return '.1%';
  if (normalized === 'percentage_points') return '+.1f';
  if (normalized === 'correlation') return '.2f';
  if (/\bbrl\b/.test(normalized)) return ',.2f';
  if (['days', 'points', 'kg'].includes(normalized)) return ',.2f';
  if (['orders', 'items', 'customers', 'count', 'cm3'].includes(normalized)) return ',.0f';
  return null;
}

function responsiveConfig(presentation) {
  const typography = presentation?.typography || {
    axisLabel:12,axisTitle:12,legendLabel:12,legendTitle:12,
  };
  return {
    font:'Segoe UI, Microsoft YaHei, sans-serif',
    view:{stroke:null},
    axis:{domain:false,ticks:false,labelColor:'#64748b',titleColor:'#475569',
      labelFontSize:typography.axisLabel,titleFontSize:typography.axisTitle,titleFontWeight:500,
      labelPadding:8,titlePadding:12,gridColor:'#edf1f5',tickCount:5},
    axisDiscrete:{grid:false,labelAngle:0,labelLimit:180},
    legend:{orient:'top',direction:'horizontal',columns:presentation?.legendColumns || 2,
      titleFontSize:typography.legendTitle,titleColor:'#64748b',titleFontWeight:600,
      labelFontSize:typography.legendLabel,labelColor:'#475569',labelLimit:180,symbolSize:80,padding:0,offset:12},
    bar:{color:'#447b9f',binSpacing:2},
    line:{strokeWidth:typography.axisLabel >= 14 ? 2.5 : 2},
    point:{size:typography.axisLabel >= 14 ? 48 : 40,filled:true},
  };
}

function filterMetadata(description, field) {
  const indexed = description.dimension_index?.[field];
  if (indexed) return indexed;

  const categories = Array.isArray(description.dimensions)
    ? [description.dimensions]
    : Object.values(description.dimensions || {});
  for (const entries of categories) {
    if (Array.isArray(entries)) {
      const metadata = entries.find((entry) => entry?.field === field);
      if (metadata) return metadata;
    } else if (entries?.[field]) {
      return entries[field];
    }
  }

  for (const resource of description.resources || []) {
    const fields = resource?.fields;
    if (Array.isArray(fields)) {
      const metadata = fields.find((entry) => entry?.field === field);
      if (metadata) return metadata;
    } else if (fields?.[field]) {
      return fields[field];
    }
  }
  return null;
}

function formatList(value) {
  return (Array.isArray(value) ? value : [value]).map(formatValue).join(', ');
}

function formatValue(value) {
  return value === null || value === undefined ? 'missing' : String(value);
}
