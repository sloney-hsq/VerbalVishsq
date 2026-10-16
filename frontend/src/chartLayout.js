import {chartColumnCount} from './chartGrid.js';

export const DEFAULT_CHART_HEIGHT = 300;
export const HEATMAP_PAGE_SIZE = 20;
export const HEATMAP_PAGE_THRESHOLD = 24;

const DISCRETE_TYPES = new Set(['nominal','ordinal','temporal']);

export function orderedDomain(view, field) {
  const declared = view?.columns?.[field]?.sort_order;
  if (Array.isArray(declared)) return [...declared];
  const seen = new Set();
  const values = [];
  for (const row of view?.data || []) {
    const value = row?.[field];
    if (value !== null && value !== undefined && !seen.has(value)) {
      seen.add(value);
      values.push(value);
    }
  }
  return values;
}

export function chartLayoutForView(view, availableWidth = 0) {
  const encoding = view?.visual?.encoding || {};
  const yField = encoding.y || view?.y_field;
  const xField = encoding.x || view?.x_field;
  const yDiscrete = DISCRETE_TYPES.has(view?.columns?.[yField]?.type);
  const isCategoryHeatmap = view?.chart_type === 'heatmap' && view?.result_kind !== 'binned_2d' && yDiscrete;
  const yDomain = isCategoryHeatmap ? orderedDomain(view,yField) : [];
  const paging = isCategoryHeatmap && yDomain.length > HEATMAP_PAGE_THRESHOLD;
  const isFacet = Boolean(encoding.facet);
  const horizontalBarRows = view?.chart_type === 'bar' && view?.columns?.[xField]?.type === 'quantitative'
    && DISCRETE_TYPES.has(view?.columns?.[yField]?.type) ? orderedDomain(view,yField).length : 0;
  const tallBar = horizontalBarRows > 20;
  const categoryDomain = isCategoryHeatmap ? yDomain : tallBar ? orderedDomain(view,yField) : [];
  const categoryPageSize = isCategoryHeatmap ? HEATMAP_PAGE_SIZE : 14;
  const categoryPaging = paging || tallBar;
  const seriesField = encoding.color || view?.color;
  const seriesCount = seriesField ? orderedDomain(view,seriesField).length : 0;
  const dense = paging || isFacet || isMultiSeriesLine(view) && seriesCount > 6;
  const columns = chartColumnCount(availableWidth);
  const twoColumns = columns > 1;
  const cardWidth = (Number(availableWidth) - (columns - 1) * 16) / columns;
  const visibleRows = paging ? HEATMAP_PAGE_SIZE : Math.max(1,yDomain.length);
  return {
    columnSpan: dense && twoColumns ? isCategoryHeatmap ? columns : 2 : 1,
    tier: paging ? 'matrix' : tallBar ? 'tall' : dense ? 'standard' : 'compact',
    cardHeight: paging || tallBar ? 600 : dense ? 420 : 360,
    plotHeight: isCategoryHeatmap ? 72 + visibleRows * 22 : tallBar ? 62 + horizontalBarRows * 18 : DEFAULT_CHART_HEIGHT,
    plotMinWidth: isCategoryHeatmap ? Math.max(420, orderedDomain(view,xField).length * 44 + 260) : 0,
    facetColumns:isFacet && twoColumns ? 2 : 1,
    legendColumns:cardWidth >= 560 ? 3 : cardWidth >= 400 ? 2 : 1,
    scrollY:tallBar,
    category:{enabled:categoryPaging,pageSize:categoryPageSize,
      pageCount:categoryPaging ? Math.ceil(categoryDomain.length / categoryPageSize) : 1,
      field:yField,domain:categoryDomain},
    heatmap:{enabled:paging,pageSize:HEATMAP_PAGE_SIZE,pageCount:paging ? Math.ceil(yDomain.length / HEATMAP_PAGE_SIZE) : 1,
      field:yField,domain:yDomain},
  };
}

export function heatmapPresentation(view, state = {}, availableWidth = 0) {
  const layout = chartLayoutForView(view,availableWidth);
  const policy = layout.category;
  const domain = policy.domain;
  const pageCount = Math.max(1,policy.pageCount);
  const pageIndex = Math.min(Math.max(0,Number(state.pageIndex) || 0),pageCount - 1);
  const mode = state.mode === 'all' ? 'all' : 'paged';
  const visibleDomain = mode === 'all' || !policy.enabled ? domain
    : domain.slice(pageIndex * policy.pageSize,(pageIndex + 1) * policy.pageSize);
  const visible = new Set(visibleDomain);
  const field = policy.field;
  const data = (view?.data || []).map((row,index) => ({...row,__source_index:index}))
    .filter(row => !policy.enabled || mode === 'all' || visible.has(row[field]));
  const colorField = view?.visual?.encoding?.color;
  const colorValues = (view?.data || []).map(row => row?.[colorField]).filter(Number.isFinite);
  const colorDomain = colorValues.length ? [Math.min(...colorValues),Math.max(...colorValues)] : null;
  const selections = Object.values(view?.selection_highlights || {}).flat();
  const selectionOffPage = mode === 'paged' && selections.some(selection => {
    const selectedField = view?.visual?.encoding?.[selection.field] || selection.field;
    return selectedField === field && selection.op === 'eq' && !visible.has(selection.value);
  });
  const pagedBar = view?.chart_type === 'bar' && policy.enabled;
  const xField = view?.visual?.encoding?.x;
  const logScale = view?.visual?.scales?.x === 'log';
  const barValues = pagedBar ? (view.data || []).map(row => row[xField])
    .filter(value => Number.isFinite(value) && (!logScale || value > 0)) : [];
  const valueDomain = barValues.length ? [
    Math.min(...barValues, ...(logScale ? [] : [0])),
    Math.max(...barValues, ...(logScale ? [] : [0])),
  ] : null;
  return {...layout,mode,pageIndex,pageCount,visibleDomain,data,colorDomain,selectionOffPage,
    valueDomain,
    scrollY:mode === 'all' && policy.enabled,
    plotHeight:pagedBar ? 62 + Math.max(1,visibleDomain.length) * 19
      : mode === 'all' ? 72 + Math.max(1,domain.length) * 20 : layout.plotHeight};
}

export function chartHeightForView(view) {
  return chartLayoutForView(view,0).plotHeight;
}

export function isMultiSeriesLine(view) {
  return view?.chart_type === 'line' && Boolean(view?.color || view?.visual?.encoding?.color);
}
