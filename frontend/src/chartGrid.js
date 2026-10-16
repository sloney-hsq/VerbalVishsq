// Pack natural-height cards without stretching shorter charts to their neighbours.
export function packChartCards(cards, columns = 2, gap = 16) {
  const bottoms = Array(Math.max(1, columns)).fill(0);
  return cards.map(card => {
    const span = Math.min(bottoms.length, Math.max(1, card.span || 1));
    let column = 0;
    let top = Infinity;
    for (let start = 0; start <= bottoms.length - span; start += 1) {
      const candidate = Math.max(...bottoms.slice(start, start + span));
      if (candidate < top) { top = candidate; column = start; }
    }
    const rowSpan = Math.max(1, Math.ceil(card.height + gap));
    for (let index = column; index < column + span; index += 1) bottoms[index] = top + rowSpan;
    return {column: column + 1, row: top + 1, rowSpan, span};
  });
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
      const columns = element.clientWidth >= 880 ? 2 : 1;
      element.style.gridTemplateColumns = `repeat(${columns}, minmax(0, 1fr))`;
      const cards = children.map(child => ({
        height: child.getBoundingClientRect().height,
        span: Number(child.dataset.layoutSpan) || 1,
      }));
      packChartCards(cards, columns).forEach((position, index) => {
        const child = children[index];
        child.style.gridColumn = `${position.column} / span ${position.span}`;
        child.style.gridRow = `${position.row} / span ${position.rowSpan}`;
      });
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
