import { applyHighlightToSpec } from './highlightSpec.js';
import { chartHeightForView } from './chartLayout.js';
import { buildChartSpec } from './chartSpecs.js';

export function formatFilter(filter, description = {}) {
  const metadata = filterMetadata(description, filter.field);
  const label = metadata?.label || filter.field;
  const op = filter.op;
  if (op === 'is_null') return `${label} is missing`;
  if (op === 'in') return `${label} in ${formatList(filter.value)}`;
  if (op === 'between') {
    const [start, end] = Array.isArray(filter.value) ? filter.value : [filter.value, undefined];
    return `${label} between ${formatValue(start)} and ${formatValue(end)}`;
  }
  const operators = {eq:'=', neq:'≠', gte:'≥', lte:'≤', gt:'>', lt:'<'};
  return `${label} ${operators[op] || op} ${formatValue(filter.value)}`;
}

/** Encodings follow the interface result, never a hard-coded domain field list. */
export function createSpec(view, highlightElement = null) {
  if (view.visual) {
    const spec = buildChartSpec(view);
    return ['bar','line','scatter'].includes(view.visual.type)
      ? applyHighlightToSpec(spec, view, highlightElement) : spec;
  }
  const encoding = (field, channel = 'axis') => {
    const metadata = view.columns?.[field];
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
  if (!['bar', 'line', 'scatter'].includes(view.chart_type)) throw new Error('Unsupported chart type');
  const x = encoding(view.x_field), y = encoding(view.y_field);
  const tooltip = [encoding(view.x_field, 'tooltip'), encoding(view.y_field, 'tooltip')];
  const spec = {
    $schema: 'https://vega.github.io/schema/vega-lite/v6.json',
    width: 'container', height: chartHeightForView(view),
    autosize: {type: 'fit', contains: 'padding', resize: true},
    data: {values: (view.data || []).map(row => ({...row}))},
    mark: view.chart_type === 'scatter' ? {type:'circle', tooltip:true, opacity:0.62}
      : view.chart_type === 'line' ? {type:'line', point:true, tooltip:true}
        : {type:'bar', tooltip:true, cornerRadiusEnd:2},
    encoding: {x, y, tooltip},
  };
  const describedFields = [...new Set([view.x_field, view.y_field, view.color].filter(Boolean))];
  spec.usermeta = {
    columns: Object.fromEntries(describedFields.map(field => [field, {...view.columns[field]}])),
  };
  const descriptions = describedFields
    .map(field => view.columns[field]?.description)
    .filter(Boolean);
  if (descriptions.length) spec.description = descriptions.join(' ');
  if (view.chart_type === 'line') x.sort = 'ascending';
  if (view.chart_type === 'bar' && x.type === 'nominal') x.sort = '-y';
  if (view.color) {
    spec.encoding.color = encoding(view.color, 'legend');
    tooltip.push(encoding(view.color, 'tooltip'));
    if (view.chart_type === 'line') spec.encoding.detail = {field:view.color};
  }
  return applyHighlightToSpec(spec, view, highlightElement);
}

function formatForUnit(unit) {
  const normalized = String(unit || '').trim().toLowerCase();
  if (normalized === 'ratio') return '.1%';
  if (/\bbrl\b/.test(normalized)) return ',.2f';
  if (['days', 'points', 'kg'].includes(normalized)) return ',.2f';
  if (['orders', 'items', 'customers', 'count', 'cm3'].includes(normalized)) return ',.0f';
  return null;
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
