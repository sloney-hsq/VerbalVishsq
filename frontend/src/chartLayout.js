export const DEFAULT_CHART_HEIGHT = 270;
export const MAX_CHART_HEIGHT = 290;

/** Adjust internal plot height without changing a card's grid placement. */
export function chartHeightForView(view) {
  const rows = Array.isArray(view?.data) ? view.data.length : 0;
  const isCategoryBar = (
    view?.chart_type === "bar" &&
    view?.orientation === "horizontal"
  );

  if (!isCategoryBar) return DEFAULT_CHART_HEIGHT;

  const estimatedHeight = 62 + rows * 15;
  return Math.min(
    MAX_CHART_HEIGHT,
    Math.max(DEFAULT_CHART_HEIGHT, estimatedHeight),
  );
}

export function isMultiSeriesLine(view) {
  return view?.chart_type === "line" && Boolean(view?.color);
}
