export function chartColumnCount(width) {
  return Number(width) >= 1440 ? 5 : Number(width) >= 880 ? 2 : 1;
}

export function chartDisplayNumbers(views) {
  const matrix = view => view.chart_type === 'heatmap' && view.result_kind !== 'binned_2d';
  return Object.fromEntries([...views.filter(view => !matrix(view)),...views.filter(matrix)]
    .map((view,index) => [view.id,index + 1]));
}

// Pack natural-height cards without stretching shorter charts to their neighbours.
export function packChartCards(cards, columns = 2, gap = 16, availableHeight = 0) {
  const isMatrix = card => card.chartType === 'heatmap' && card.resultKind !== 'binned_2d';
  const matrices = cards.filter(isMatrix);
  // A single tall category matrix beside at most eight equal comparison cards.
  if (columns === 5 && availableHeight > 0 && matrices.length === 1 && cards.length <= 9
    && cards.every(card => !(card.span > 1))) {
    const rowGap = Math.ceil(gap);
    const height = Math.max(320,Math.floor((availableHeight - rowGap) / 2));
    let index = 0;
    return cards.map(card => {
      if (isMatrix(card)) return {column:5,row:1,rowSpan:height * 2 + rowGap,span:1,height:height * 2 + rowGap};
      const slot = index++;
      return {column:slot % 4 + 1,row:Math.floor(slot / 4) * (height + rowGap) + 1,rowSpan:height,span:1,height};
    });
  }
  const bottoms = Array(Math.max(1, columns)).fill(0);
  const heatmapLane = bottoms.length >= 4 && cards.some(isMatrix);
  return cards.map(card => {
    const inHeatmapLane = heatmapLane && isMatrix(card);
    const usableColumns = heatmapLane ? bottoms.length - 1 : bottoms.length;
    const span = inHeatmapLane ? 1 : Math.min(usableColumns, Math.max(1, card.span || 1));
    const firstColumn = inHeatmapLane ? bottoms.length - 1 : 0;
    const lastColumn = inHeatmapLane ? firstColumn : usableColumns - span;
    let column = 0;
    let top = Infinity;
    for (let start = firstColumn; start <= lastColumn; start += 1) {
      const candidate = Math.max(...bottoms.slice(start, start + span));
      if (candidate < top) { top = candidate; column = start; }
    }
    const rowSpan = Math.max(1, Math.ceil(card.height + gap));
    for (let index = column; index < column + span; index += 1) bottoms[index] = top + rowSpan;
    return {column: column + 1, row: top + 1, rowSpan, span};
  });
}

export function packedContentHeight(positions) {
  return positions.reduce((bottom, position) => Math.max(bottom, position.row - 1 + position.rowSpan), 0);
}

const instances = new WeakMap();

export const vChartGrid = {
  mounted(element) {
    let frame = 0;
    let disposed = false;
    const observed = new Set();
    const schedule = () => {
      if (!disposed && !frame) frame = requestAnimationFrame(layout);
    };
    const observer = new ResizeObserver(schedule);
    function layout() {
      frame = 0;
      if (disposed || !element.clientWidth) return;
      const children = [...element.children];
      for (const child of observed) if (!children.includes(child)) {
        observer.unobserve(child); observed.delete(child);
      }
      for (const child of children) if (!observed.has(child)) {
        observer.observe(child); observed.add(child);
      }
      const columns = chartColumnCount(element.clientWidth);
      element.style.gridTemplateColumns = `repeat(${columns}, minmax(0, 1fr))`;
      const cards = children.map(child => ({
        height: child.getBoundingClientRect().height,
        span: Number(child.dataset.layoutSpan) || 1,
        chartType: child.dataset.chartType,
        resultKind: child.dataset.resultKind,
      }));
      const gap = Number.parseFloat(getComputedStyle(element).columnGap) || 16;
      const style = getComputedStyle(element);
      const height = element.clientHeight - (Number.parseFloat(style.paddingTop) || 0) - (Number.parseFloat(style.paddingBottom) || 0);
      const positions = packChartCards(cards, columns, gap, height);
      const equalGrid = positions.some(position => position.height);
      element.style.gridTemplateRows = equalGrid ? 'repeat(2, minmax(320px, 1fr))' : '';
      element.style.rowGap = equalGrid ? `${gap}px` : '0';
      positions.forEach((position, index) => {
        const child = children[index];
        child.style.gridColumn = `${position.column} / span ${position.span}`;
        child.style.gridRow = equalGrid
          ? `${position.row === 1 ? 1 : 2} / span ${position.column === 5 ? 2 : 1}`
          : `${position.row} / span ${position.rowSpan}`;
        child.style.height = equalGrid ? '100%' : '';
        child.dataset.bounded = String(Boolean(position.height));
      });
      element.dataset.canvasFit = String(packedContentHeight(positions) <= height);
    }
    const mutations = new MutationObserver(schedule);
    mutations.observe(element, {childList: true});
    observer.observe(element);
    instances.set(element, {schedule, dispose() {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      mutations.disconnect();
    }});
    schedule();
  },
  updated(element) { instances.get(element)?.schedule(); },
  unmounted(element) { instances.get(element)?.dispose(); instances.delete(element); },
};
