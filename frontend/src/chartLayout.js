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
  const dense = paging || Boolean(encoding.facet) || isMultiSeriesLine(view);
  const twoColumns = Number(availableWidth) >= 880;
  const visibleRows = paging ? HEATMAP_PAGE_SIZE : Math.max(1,yDomain.length);
  return {
    columnSpan: dense && twoColumns ? 2 : 1,
    tier: paging ? 'matrix' : dense ? 'standard' : 'compact',
    cardHeight: paging ? 600 : dense ? 420 : 360,
    plotHeight: isCategoryHeatmap ? 72 + visibleRows * 22 : DEFAULT_CHART_HEIGHT,
    plotMinWidth: isCategoryHeatmap ? Math.max(420, orderedDomain(view,xField).length * 44 + 260) : 0,
    heatmap:{enabled:paging,pageSize:HEATMAP_PAGE_SIZE,pageCount:paging ? Math.ceil(yDomain.length / HEATMAP_PAGE_SIZE) : 1,
      field:yField,domain:yDomain},
  };
}

export function heatmapPresentation(view, state = {}, availableWidth = 0) {
  const layout = chartLayoutForView(view,availableWidth);
  const domain = layout.heatmap.domain;
  const pageCount = Math.max(1,layout.heatmap.pageCount);
  const pageIndex = Math.min(Math.max(0,Number(state.pageIndex) || 0),pageCount - 1);
  const mode = state.mode === 'all' ? 'all' : 'paged';
  const visibleDomain = mode === 'all' || !layout.heatmap.enabled ? domain
    : domain.slice(pageIndex * HEATMAP_PAGE_SIZE,(pageIndex + 1) * HEATMAP_PAGE_SIZE);
  const visible = new Set(visibleDomain);
  const field = layout.heatmap.field;
  const data = (view?.data || []).map((row,index) => ({...row,__source_index:index}))
    .filter(row => !layout.heatmap.enabled || mode === 'all' || visible.has(row[field]));
  const colorField = view?.visual?.encoding?.color;
  const colorValues = (view?.data || []).map(row => row?.[colorField]).filter(Number.isFinite);
  const colorDomain = colorValues.length ? [Math.min(...colorValues),Math.max(...colorValues)] : null;
  const selections = Object.values(view?.selection_highlights || {}).flat();
  const selectionOffPage = mode === 'paged' && selections.some(selection => {
    const selectedField = view?.visual?.encoding?.[selection.field] || selection.field;
    return selectedField === field && selection.op === 'eq' && !visible.has(selection.value);
  });
  return {...layout,mode,pageIndex,pageCount,visibleDomain,data,colorDomain,selectionOffPage,
    plotHeight:mode === 'all' ? 72 + Math.max(1,domain.length) * 20 : layout.plotHeight};
}

export function chartHeightForView(view) {
  return chartLayoutForView(view,0).plotHeight;
}

export function isMultiSeriesLine(view) {
  return view?.chart_type === 'line' && Boolean(view?.color || view?.visual?.encoding?.color);
}
