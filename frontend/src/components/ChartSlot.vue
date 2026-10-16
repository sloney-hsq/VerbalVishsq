<template>
  <article
    class="chart-card"
    :class="[`chart-card--${layout.tier}`, {
      'chart-card--highlighted': view.highlighted,
      'chart-card--dimmed': isDimmed,
      'chart-card--multi-series': isMultiSeriesLine(view),
    }]"
    :style="cardStyle"
  >
    <header class="chart-card__header">
      <div class="chart-card__identity">
        <span class="view-id">{{ viewLabel }}</span>
        <span class="chart-type">{{ chartTypeLabel }}</span>
      </div>
      <div class="chart-card__badges">
        <span v-if="view.top_n || view.limit">Top {{ view.top_n || view.limit }}</span>
        <span v-if="view.normalize">100% stacked</span>
        <span v-if="view.visual?.stack === 'normalize'">100% stacked</span>
        <span v-if="view.scope_mode === 'snapshot'">Fixed scope</span>
        <span v-if="view.metadata?.sampling?.sampled">Sampled {{ view.metadata.sampling.actual_points }} points</span>
        <span v-if="view.metadata?.overlap_count > 0">Overlap {{ view.metadata.overlap_count }}</span>
        <span v-if="view.metadata?.valid_count != null && view.metadata?.missing_count > 0">{{ view.metadata.valid_count }} valid / {{ view.metadata.missing_count }} missing</span>
        <span v-if="Object.keys(view.selection_filters || {}).length">Filtered by selection</span>
        <span v-if="Object.keys(view.selection_source_status || {}).length">Source removed</span>
        <span v-if="hasSharedOrder">Shared order</span>
        <span v-if="view.visual?.scales?.resolve === 'independent'">Independent scales</span>
        <span v-if="view.focus_x">Focus {{ view.focus_x }}</span>
        <span v-if="resolvedHighlight" class="highlight-badge">
          {{ resolvedHighlight.label }}
        </span>
      </div>
      <h2>{{ view.title }}</h2>
    </header>
    <nav v-if="layout.heatmap.enabled" class="heatmap-pages" aria-label="Heatmap pages">
      <button type="button" :disabled="presentation.mode === 'all' || presentation.pageIndex === 0" @click="previousPage">Previous</button>
      <span v-if="presentation.mode === 'paged'">Page {{ presentation.pageIndex + 1 }} of {{ presentation.pageCount }}</span>
      <button type="button" :disabled="presentation.mode === 'all' || presentation.pageIndex >= presentation.pageCount - 1" @click="nextPage">Next</button>
      <button type="button" :aria-pressed="presentation.mode === 'all'" @click="toggleAll">{{ presentation.mode === 'all' ? 'Paged view' : 'View all' }}</button>
      <span>{{ categoryRange }}</span>
      <span v-if="presentation.selectionOffPage">Selection is on another page</span>
    </nav>
    <div
      ref="vegaContainer"
      class="chart-card__body"
      :style="chartBodyStyle"
    ></div>
  </article>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { createSpec } from "../specFactory";
import { chartLayoutForView, heatmapPresentation, isMultiSeriesLine } from "../chartLayout";
import { resolveHighlight } from "../highlightSpec";
import { useDashboardStore } from "../stores/dashboard";

const props = defineProps({
  view: { type: Object, required: true },
  availableWidth: {type:Number,default:0},
});

const store = useDashboardStore();
const vegaContainer = ref(null);
let embeddedView = null;
let vegaEmbedPromise = null;
let renderGeneration = 0;
let renderQueue = Promise.resolve();
const pageIndex = ref(0);
const heatmapMode = ref('paged');
const layout = computed(() => chartLayoutForView(props.view,props.availableWidth));
const presentation = computed(() => heatmapPresentation(props.view,
  {pageIndex:pageIndex.value,mode:heatmapMode.value},props.availableWidth));
const domainSignature = computed(() => JSON.stringify(layout.value.heatmap.domain));
const cardStyle = computed(() => ({
  gridColumn: layout.value.columnSpan > 1 ? `span ${layout.value.columnSpan}` : 'span 1',
  minHeight:`${layout.value.cardHeight}px`,
}));
const categoryRange = computed(() => {
  const total = layout.value.heatmap.domain.length;
  if (presentation.value.mode === 'all') return `All ${total} categories`;
  const start = total ? presentation.value.pageIndex * layout.value.heatmap.pageSize + 1 : 0;
  const end = Math.min(total,start + layout.value.heatmap.pageSize - 1);
  return `${start}–${end} of ${total} categories`;
});

const activeHighlightElement = computed(() => (
  props.view.highlighted ? store.highlightElement : null
));
const resolvedHighlight = computed(() => (
  resolveHighlight(props.view, activeHighlightElement.value)
));
const isDimmed = computed(() => (
  store.highlightDimOthers &&
  store.highlightedViewIds.length > 0 &&
  !props.view.highlighted
));
const viewLabel = computed(() => {
  const match = String(props.view.id || "").match(/view(\d+)/i);
  return match ? `View ${match[1]}` : String(props.view.id || "View");
});
const chartTypeLabel = computed(() => ({
  line: "Line",
  bar: "Bar",
  scatter: "Scatter",
  heatmap: "Heatmap",
  histogram: "Histogram",
  boxplot: "Box plot",
}[props.view.chart_type] || props.view.chart_type));
const hasSharedOrder = computed(() => (
  props.view.order_contract?.mode === "shared_rank" &&
  props.view.order_contract?.verified === true
));
const chartBodyStyle = computed(() => ({minHeight:`${Math.min(presentation.value.plotHeight,512)}px`,
  maxHeight:presentation.value.mode === 'all' ? '560px' : presentation.value.scrollY ? '520px' : 'none',
  '--plot-min-width':`${presentation.value.plotMinWidth || 0}px`}));

watch(
  () => props.view,
  () => nextTick(render),
  { deep: true },
);
watch(domainSignature, () => {
  pageIndex.value = Math.min(pageIndex.value,Math.max(0,layout.value.heatmap.pageCount - 1));
});
watch([pageIndex,heatmapMode,() => props.availableWidth],() => nextTick(render));
watch(
  activeHighlightElement,
  () => nextTick(render),
  { deep: true },
);

onMounted(() => nextTick(render));
onBeforeUnmount(() => {
  renderGeneration += 1;
  clearChart();
});

function render() {
  const generation = ++renderGeneration;
  renderQueue = renderQueue
    .catch(() => undefined)
    .then(() => performRender(generation));
  return renderQueue;
}

async function performRender(generation) {
  if (!vegaContainer.value || generation !== renderGeneration) return;
  clearChart();

  try {
    const spec = createSpec(props.view, activeHighlightElement.value,presentation.value);
    const vegaEmbed = await loadVegaEmbed();
    if (!vegaContainer.value || generation !== renderGeneration) return;
    const result = await vegaEmbed(vegaContainer.value, spec, {
      actions: false,
      renderer: "svg",
      theme: "vox",
    });
    if (generation !== renderGeneration) {
      result.view?.finalize?.();
      return;
    }
    embeddedView = result.view;
  } catch (error) {
    if (generation !== renderGeneration) return;
    console.warn(`Unable to render ${props.view.id}`, error);
    vegaContainer.value.textContent = "Unable to render this view.";
  }
}

function previousPage() { pageIndex.value = Math.max(0,pageIndex.value - 1); }
function nextPage() { pageIndex.value = Math.min(presentation.value.pageCount - 1,pageIndex.value + 1); }
function toggleAll() { heatmapMode.value = heatmapMode.value === 'all' ? 'paged' : 'all'; }

function loadVegaEmbed() {
  if (!vegaEmbedPromise) {
    vegaEmbedPromise = import("vega-embed").then((module) => module.default);
  }
  return vegaEmbedPromise;
}

function clearChart() {
  embeddedView?.finalize?.();
  embeddedView = null;
  if (vegaContainer.value) vegaContainer.value.innerHTML = "";
}
</script>

<style scoped>
.chart-card {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
  padding: 11px 12px 10px;
  overflow: hidden;
  border: 1px solid #d9e1ec;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 3px 10px rgba(15, 23, 42, 0.06);
  transition: opacity 160ms ease, box-shadow 160ms ease;
}

.chart-card--highlighted {
  box-shadow: 0 0 0 2px #3b82f6, 0 2px 8px rgba(37, 99, 235, 0.13);
}

.chart-card--dimmed {
  opacity: 0.28;
}

.chart-card--matrix { height:auto; }

.chart-card__header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  min-height: 42px;
  gap: 5px 8px;
}

.chart-card__identity,
.chart-card__badges {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 5px;
}

.chart-card__badges {
  justify-content: flex-end;
  flex-wrap: wrap;
}

.view-id,
.chart-type,
.chart-card__badges span {
  display: inline-flex;
  align-items: center;
  min-height: 19px;
  padding: 2px 6px;
  overflow: hidden;
  border: 1px solid #dbe3ee;
  border-radius: 6px;
  background: #f8fafc;
  color: #526174;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.view-id {
  border-color: #bfd7ff;
  background: #eff6ff;
  color: #1d4ed8;
}

.highlight-badge {
  max-width: 200px;
  border-color: #f4c85c !important;
  background: #fffbeb !important;
  color: #92400e !important;
}

.chart-card h2 {
  grid-column: 1 / -1;
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: #1f2937;
  font-size: 12px;
  font-weight: 650;
  line-height: 1.2;
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.heatmap-pages { display:flex; align-items:center; flex-wrap:wrap; gap:6px; min-height:34px; color:#526174; font-size:11px; }
.heatmap-pages button { padding:4px 8px; border:1px solid #cbd5e1; border-radius:6px; background:#f8fafc; color:#334155; cursor:pointer; }
.heatmap-pages button:disabled { cursor:not-allowed; opacity:.45; }
.heatmap-pages button[aria-pressed="true"] { border-color:#93c5fd; background:#eff6ff; color:#1d4ed8; }

@media (max-width: 560px) {
  .chart-card__header { grid-template-columns: minmax(0,1fr); }
  .chart-card__badges { justify-content:flex-start; }
  .chart-card h2 { grid-column:1; }
}

.chart-card__body {
  flex: 1 1 auto;
  width: 100%;
  min-width: 0;
  overflow: auto;
}

.chart-card__body :deep(.vega-embed) {
  width: 100%;
  min-width: var(--plot-min-width, 0);
  max-width: 100%;
}

.chart-card__body :deep(svg) {
  display: block;
  max-width: 100%;
}
</style>
