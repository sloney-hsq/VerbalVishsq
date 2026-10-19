import {chartColumnCount} from './chartGrid.js';

export const DEFAULT_CHART_HEIGHT = 300;
export const HEATMAP_PAGE_SIZE = 20;
export const HEATMAP_PAGE_THRESHOLD = 24;

const GRID_GAP = 20;

const DISCRETE_TYPES = new Set(['nominal','ordinal','temporal']);

// Classic scrollbars change the content box but must not change a fixed slot.
export function chartViewportForResize(entry, bounded = false) {
  const size = entry?.borderBoxSize?.[0] ?? entry?.borderBoxSize;
  return {
    width:Math.max(0,Math.floor(size?.inlineSize ?? entry?.contentRect?.width ?? 0)),
    height:bounded ? Math.max(0,Math.floor(size?.blockSize ?? entry?.contentRect?.height ?? 0)) : 0,
  };
}

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

export function chartLayoutForView(view, availableWidth = 0, availablePlotHeight = 0) {
  const encoding = view?.visual?.encoding || {};
  const columns = chartColumnCount(availableWidth);
  const numericWidth = Math.max(0,Number(availableWidth) || 0);
  const compactCanvas = columns >= 4 && numericWidth < 2200;
  const plotBudget = Math.max(0,Number(availablePlotHeight) || 0);
  const heatmapPageSize = plotBudget ? Math.max(1,Math.floor((plotBudget - 100) / 22))
    : compactCanvas ? 12 : HEATMAP_PAGE_SIZE;
  const yField = encoding.y || view?.y_field;
  const xField = encoding.x || view?.x_field;
  const yDiscrete = DISCRETE_TYPES.has(view?.columns?.[yField]?.type);
  const xDiscrete = DISCRETE_TYPES.has(view?.columns?.[xField]?.type);
  const isCategoryHeatmap = view?.chart_type === 'heatmap' && view?.result_kind !== 'binned_2d' && yDiscrete;
  const yDomain = isCategoryHeatmap ? orderedDomain(view,yField) : [];
  const xCategoryDomain = xDiscrete ? orderedDomain(view,xField) : [];
  const xDomain = isCategoryHeatmap ? xCategoryDomain : [];
  const paging = isCategoryHeatmap && yDomain.length > (plotBudget || compactCanvas ? heatmapPageSize : HEATMAP_PAGE_THRESHOLD);
  const isFacet = Boolean(encoding.facet);
  const horizontalBarRows = view?.chart_type === 'bar' && view?.columns?.[xField]?.type === 'quantitative'
    && DISCRETE_TYPES.has(view?.columns?.[yField]?.type) ? orderedDomain(view,yField).length : 0;
  const tallBar = horizontalBarRows > 20;
  const categoryDomain = isCategoryHeatmap ? yDomain : tallBar ? orderedDomain(view,yField) : [];
  const categoryPageSize = isCategoryHeatmap ? heatmapPageSize : 14;
  const categoryPaging = paging || tallBar;
  const seriesField = encoding.color || view?.color;
  const seriesCount = seriesField ? orderedDomain(view,seriesField).length : 0;
  const dense = paging || isFacet || isMultiSeriesLine(view) && seriesCount > 6;
  const twoColumns = columns > 1;
  const columnWidth = numericWidth > 0
    ? (numericWidth - (columns - 1) * GRID_GAP) / columns
    : 0;
  const broadHeatmap = isCategoryHeatmap && xDomain.length >= 6;
  const compactHeatmapNeedsRoom = isCategoryHeatmap && columns === 2 && columnWidth < 600;
  const rightLaneHeatmap = view?.chart_type === 'heatmap' && columns >= 4;
  const columnSpan = !rightLaneHeatmap && dense && twoColumns && (!isCategoryHeatmap || broadHeatmap || compactHeatmapNeedsRoom) ? 2 : 1;
  const cardWidth = columnWidth > 0
    ? columnWidth * columnSpan + GRID_GAP * (columnSpan - 1)
    : 0;
  const axisLabelLimit = rightLaneHeatmap && isCategoryHeatmap
    ? Math.min(280,Math.max(90,Math.floor(cardWidth * .36)))
    : numericWidth >= 2200 ? 280 : 220;
  const heatmapGradientLength = Math.min(320,Math.max(90,Math.floor(cardWidth - (isCategoryHeatmap ? axisLabelLimit : 60) - 110)));
  const typography = responsiveTypography(cardWidth);
  const rowHeight = typography.axisLabel >= 14 ? 26 : typography.axisLabel >= 13 ? 24 : 22;
  const visibleRows = paging ? heatmapPageSize : Math.max(1,yDomain.length);
  const isVerticalCategoricalBar = view?.chart_type === 'bar' && xDiscrete
    && view?.columns?.[yField]?.type === 'quantitative';
  const longestXLabel = xCategoryDomain.reduce((length,value) => Math.max(length,String(value).length),0);
  const rotateCategoryLabels = isVerticalCategoricalBar && xCategoryDomain.length >= 8
    && (longestXLabel >= 12 || cardWidth / xCategoryDomain.length < 90);
  const categoryAxis = rotateCategoryLabels ? {
    labelAngle:cardWidth < 400 ? -55 : -32,labelAlign:'right',labelOverlap:false,
    labelLimit:cardWidth >= 900 ? 180 : 130,labelPadding:10,
  } : null;
  const standardPlotHeight = (numericWidth > 0
    ? Math.round(Math.min(420,Math.max(columns >= 4 ? 200 : 280,columnWidth * .48)))
    : DEFAULT_CHART_HEIGHT) + (categoryAxis ? cardWidth < 400 ? 72 : 48 : 0);
  return {
    columns,
    columnSpan,
    tier: paging ? 'matrix' : tallBar ? 'tall' : dense ? 'standard' : 'compact',
    cardHeight: paging || tallBar ? numericWidth >= 2200 ? 680 : 600 : dense ? 500 : standardPlotHeight + 120,
    plotHeight: isCategoryHeatmap ? 84 + visibleRows * rowHeight : tallBar ? 62 + horizontalBarRows * 18 : standardPlotHeight,
    plotWidth:isCategoryHeatmap && !broadHeatmap && !rightLaneHeatmap ? Math.max(260,xDomain.length * 92) : null,
    plotMinWidth: isCategoryHeatmap && !rightLaneHeatmap
      ? Math.max(420, xDomain.length * (typography.axisLabel >= 14 ? 52 : 44) + 260)
      : 0,
    facetColumns:isFacet && twoColumns ? 2 : 1,
    facetWidth:cardWidth >= 900 ? 340 : cardWidth >= 600 ? 280 : 240,
    facetHeight:cardWidth >= 900 ? 260 : 220,
    legendColumns:cardWidth >= 560 ? 3 : cardWidth >= 400 ? 2 : 1,
    bodyMaxHeight:numericWidth >= 2200 ? 760 : numericWidth >= 1200 ? 640 : 560,
    axisLabelLimit,
    heatmapLegend:rightLaneHeatmap ? {gradientLength:heatmapGradientLength,
      titleLineLength:cardWidth < 600 ? 18 : 32,tickCount:heatmapGradientLength < 220 ? 3 : 5} : null,
    categoryAxis,
    typography,
    rowHeight,
    scrollY:tallBar,
    category:{enabled:categoryPaging,pageSize:categoryPageSize,
      pageCount:categoryPaging ? Math.ceil(categoryDomain.length / categoryPageSize) : 1,
      field:yField,domain:categoryDomain},
    heatmap:{enabled:paging,pageSize:heatmapPageSize,pageCount:paging ? Math.ceil(yDomain.length / heatmapPageSize) : 1,
      field:yField,domain:yDomain},
  };
}

export function heatmapPresentation(view, state = {}, availableWidth = 0, availablePlotHeight = 0, availablePlotWidth = 0) {
  const layout = chartLayoutForView(view,availableWidth,availablePlotHeight);
  const policy = layout.category;
  const domain = policy.domain;
  const pageCount = Math.max(1,policy.pageCount);
  const pageIndex = Math.min(Math.max(0,Number(state.pageIndex) || 0),pageCount - 1);
  const mode = state.mode === 'all' && layout.columns < 4 ? 'all' : 'paged';
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
    // Explicit inset avoids SVG rounding a fractional container width upward.
    fitWidth:availablePlotHeight > 0 && availablePlotWidth > 0 ? Math.max(1,Math.floor(availablePlotWidth) - 2) : null,
    scrollY:mode === 'all' && policy.enabled,
    plotHeight:availablePlotHeight > 0 && !view?.visual?.encoding?.facet ? Math.max(180,Math.floor(availablePlotHeight) - 2)
      : pagedBar ? 62 + Math.max(1,visibleDomain.length) * Math.max(19,layout.rowHeight - 3)
      : mode === 'all' ? 84 + Math.max(1,domain.length) * layout.rowHeight : layout.plotHeight};
}

export function chartHeightForView(view) {
  return chartLayoutForView(view,0).plotHeight;
}

export function isMultiSeriesLine(view) {
  return view?.chart_type === 'line' && Boolean(view?.color || view?.visual?.encoding?.color);
}

function responsiveTypography(cardWidth) {
  if (cardWidth >= 600) {
    return {axisLabel:14,axisTitle:14,legendLabel:13,legendTitle:13};
  }
  if (cardWidth >= 500) {
    return {axisLabel:13,axisTitle:13,legendLabel:12,legendTitle:12};
  }
  return {axisLabel:12,axisTitle:12,legendLabel:12,legendTitle:12};
}
