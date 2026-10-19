<template>
  <article
    class="chart-card"
    :class="[`chart-card--${layout.tier}`, {
      'chart-card--highlighted': view.highlighted,
      'chart-card--dimmed': isDimmed,
      'chart-card--multi-series': isMultiSeriesLine(view),
    }]"
    :data-layout-span="layout.columnSpan"
    :data-chart-type="view.chart_type"
    :data-result-kind="view.result_kind"
  >
    <header class="chart-card__header">
      <div class="chart-card__heading">
        <div class="chart-card__title-block">
          <span v-if="displayNumber" class="chart-card__number" :aria-label="`View ${displayNumber}`">{{ displayNumber }}</span>
          <h2 :title="view.title">{{ view.title }}</h2>
        </div>
        <details class="chart-card__info" @keydown.esc="$event.currentTarget.open = false">
          <summary :aria-label="`Chart details: ${view.title}`" :title="chartDetailsTooltip">ⓘ</summary>
          <div class="chart-card__info-panel">
            <strong>{{ view.title }}</strong>
            <p class="chart-card__meta">{{ chartSummary }}</p>
            <p>{{ chartTypeLabel }}</p>
            <p v-if="view.metadata?.observation_unit">Observation unit: {{ humanizeNotice(view.metadata.observation_unit) }}</p>
          </div>
        </details>
      </div>
      <div class="chart-card__badges" aria-label="Chart metadata">
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
    </header>
    <details v-if="metadataNotices.length" class="analysis-notices">
      <summary>{{ metadataNotices.length }} analysis {{ metadataNotices.length === 1 ? 'notice' : 'notices' }}</summary>
      <ul><li v-for="(notice,index) in metadataNotices" :key="index">{{ notice }}</li></ul>
    </details>
    <nav v-if="layout.category.enabled" class="heatmap-pages" :aria-label="view.chart_type === 'heatmap' ? 'Heatmap pages' : 'Category pages'">
      <div class="heatmap-pages__status" aria-live="polite">
        <strong>{{ categoryRange }}</strong>
        <span v-if="presentation.selectionOffPage" class="heatmap-pages__notice">Selection is on another page</span>
      </div>
      <div class="heatmap-pages__actions">
        <button type="button" aria-label="Previous page" title="Previous page" :disabled="presentation.mode === 'all' || presentation.pageIndex === 0" @click="previousPage">‹</button>
        <button type="button" aria-label="Next page" title="Next page" :disabled="presentation.mode === 'all' || presentation.pageIndex >= presentation.pageCount - 1" @click="nextPage">›</button>
        <button v-if="layout.columns < 4" type="button" :aria-label="presentation.mode === 'all' ? 'Show paged categories' : 'Show all categories'" :title="presentation.mode === 'all' ? 'Show paged categories' : 'Show all categories'" :aria-pressed="presentation.mode === 'all'" @click="toggleAll">{{ presentation.mode === 'all' ? 'Paged' : 'Show all' }}</button>
      </div>
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
import { chartLayoutForView, chartViewportForResize, heatmapPresentation, isMultiSeriesLine } from "../chartLayout";
import { resolveHighlight } from "../highlightSpec";
import { useDashboardStore } from "../stores/dashboard";
import { createChartRenderLifecycle } from "../chartRenderLifecycle.js";

const props = defineProps({
  view: { type: Object, required: true },
  availableWidth: {type:Number,default:0},
  displayNumber: {type:Number,default:null},
  renderRequest: { type: Object, default: null },
});
const emit = defineEmits(['rendered', 'render-failed']);

const store = useDashboardStore();
const renderLifecycle = createChartRenderLifecycle((type, payload) => emit(type, payload));
const vegaContainer = ref(null);
let embeddedView = null;
let vegaEmbedPromise = null;
let renderGeneration = 0;
let renderQueue = Promise.resolve();
let bodyObserver = null;
const observedWidth = ref(0);
const observedHeight = ref(0);
const pageIndex = ref(0);
const heatmapMode = ref('paged');
const layout = computed(() => chartLayoutForView(props.view,props.availableWidth,observedHeight.value));
const presentation = computed(() => heatmapPresentation(props.view,
  {pageIndex:pageIndex.value,mode:heatmapMode.value},props.availableWidth,observedHeight.value,observedWidth.value));
const domainSignature = computed(() => JSON.stringify(layout.value.category.domain));
const categoryRange = computed(() => {
  const total = layout.value.category.domain.length;
  if (presentation.value.mode === 'all') return `All ${total} categories`;
  const start = total ? presentation.value.pageIndex * layout.value.category.pageSize + 1 : 0;
  const end = Math.min(total,start + layout.value.category.pageSize - 1);
  return `${start}–${end} of ${total} categories`;
});
const chartSummary = computed(() => {
  const encoding = props.view.visual?.encoding || {};
  const measureField = [encoding.color,encoding.y,encoding.x,props.view.y_field,props.view.x_field]
    .find(field => props.view.columns?.[field]?.type === 'quantitative');
  const metadata = props.view.columns?.[measureField] || {};
  const declaredLabel = metadata.label
    ? metadata.label
    : metadata.source_field ? humanizeNotice(metadata.source_field) : '';
  const measure = declaredLabel ? `${declaredLabel}${metadata.unit ? ` (${metadata.unit})` : ''} · ` : '';
  const rows = props.view.data?.length || 0;
  return `${measure}${rows} result ${rows === 1 ? 'row' : 'rows'}`;
});
const chartDetailsTooltip = computed(() => [
  props.view.title, chartSummary.value, chartTypeLabel.value,
  props.view.metadata?.observation_unit
    ? `Observation unit: ${humanizeNotice(props.view.metadata.observation_unit)}` : '',
].filter(Boolean).join('\n'));
const metadataNotices = computed(() => {
  const warnings = normalizeNotices(props.view.metadata?.warnings);
  const suppressed = normalizeNotices(props.view.metadata?.comparison_suppressed_reasons)
    .map(reason => `Comparison suppressed: ${humanizeNotice(reason)}`);
  return [...warnings.map(humanizeNotice),...suppressed];
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
const chartBodyStyle = computed(() => ({
  maxHeight:presentation.value.mode === 'all' || presentation.value.scrollY
    ? `${presentation.value.bodyMaxHeight}px`
    : 'none',
  '--plot-min-width':`${presentation.value.plotMinWidth || 0}px`}));

watch(
  () => props.view,
  () => nextTick(render),
  { deep: true },
);
watch(domainSignature, () => {
  pageIndex.value = Math.min(pageIndex.value,Math.max(0,layout.value.category.pageCount - 1));
});
watch([pageIndex,heatmapMode,observedWidth,observedHeight,() => props.availableWidth],() => nextTick(render));
watch(() => props.renderRequest?.token, () => nextTick(render));
watch(
  activeHighlightElement,
  () => nextTick(render),
  { deep: true },
);

onMounted(() => {
  bodyObserver = new ResizeObserver(entries => {
    const bounded = vegaContainer.value?.parentElement.dataset.bounded === 'true';
    const size = chartViewportForResize(entries[0],bounded);
    if (size.width > 0) observedWidth.value = size.width;
    observedHeight.value = size.height;
  });
  if (vegaContainer.value) bodyObserver.observe(vegaContainer.value,{box:'border-box'});
  nextTick(render);
});
onBeforeUnmount(() => {
  renderGeneration += 1;
  renderLifecycle.dispose();
  bodyObserver?.disconnect();
  clearChart();
});

function render() {
  renderLifecycle.invalidate();
  const generation = ++renderGeneration;
  renderQueue = renderQueue
    .catch(() => undefined)
    .then(() => performRender(generation));
  return renderQueue;
}

async function performRender(generation) {
  if (!vegaContainer.value || generation !== renderGeneration) return;
  clearChart();
  const ticket = renderTicket();

  try {
    const spec = createSpec(props.view, activeHighlightElement.value,presentation.value);
    const vegaEmbed = await loadVegaEmbed();
    if (!vegaContainer.value || generation !== renderGeneration) return;
    const result = await vegaEmbed(vegaContainer.value, spec, {
      actions: false,
      renderer: "svg",
    });
    if (generation !== renderGeneration) {
      result.view?.finalize?.();
      return;
    }
    embeddedView = result.view;
    if (ticket) await renderLifecycle.complete(ticket, result.view);
  } catch (error) {
    if (generation !== renderGeneration) return;
    console.warn(`Unable to render ${props.view.id}`, error);
    vegaContainer.value.textContent = "Unable to render this view.";
    if (ticket) renderLifecycle.fail(ticket, 'embed_failed');
  }
}

function renderTicket() {
  const request = props.renderRequest;
  const expected = request?.expected_views?.find(item => item.view_id === props.view.id);
  if (!expected || expected.view_revision !== props.view.view_revision) return null;
  return renderLifecycle.start({
    renderToken: request.token,
    dashboardRevision: request.dashboard_revision,
    viewId: props.view.id,
    viewRevision: props.view.view_revision,
    presentation: {
      mode: presentation.value.mode,
      page_index: presentation.value.mode === 'paged' ? presentation.value.pageIndex : 0,
    },
  });
}

function previousPage() { pageIndex.value = Math.max(0,pageIndex.value - 1); }
function nextPage() { pageIndex.value = Math.min(presentation.value.pageCount - 1,pageIndex.value + 1); }
function toggleAll() { heatmapMode.value = heatmapMode.value === 'all' ? 'paged' : 'all'; }

function normalizeNotices(value) {
  if (value === null || value === undefined || value === '') return [];
  if (Array.isArray(value)) return value.flatMap(normalizeNotices);
  if (typeof value === 'object') return Object.entries(value).flatMap(([key,item]) =>
    normalizeNotices(item).map(detail => `${key}: ${detail}`));
  return [String(value)];
}

function humanizeNotice(value) {
  const text = String(value).replaceAll('_',' ');
  return text.replace(/^./,letter => letter.toUpperCase());
}

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
  padding: clamp(10px, 0.4vw, 16px) clamp(14px, 0.6vw, 22px);
  overflow: hidden;
  border: 1px solid var(--vv-border, #dfe6ef);
  border-radius: 8px;
  background: var(--vv-surface, #fff);
  transition: opacity 160ms ease, box-shadow 160ms ease;
}

.chart-card--highlighted {
  box-shadow: 0 0 0 2px var(--vv-accent, #2563eb), 0 6px 18px rgba(37, 99, 235, 0.13);
}

.chart-card--dimmed {
  opacity: 0.28;
}

.chart-card--matrix { height:auto; }

.chart-card__header {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: center;
  gap: 5px;
  margin-bottom: 6px;
}

.chart-card__heading,
.chart-card__badges {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 5px;
}

.chart-card__badges {
  justify-content: flex-start;
  flex-wrap: wrap;
}
.chart-card__badges:empty { display:none; }
.chart-card__heading { justify-content:space-between; gap:8px; }
.chart-card__title-block { display:flex; align-items:center; gap:8px; min-width:0; }
.chart-card__number { display:inline-grid; place-items:center; flex:0 0 auto; width:26px; height:26px; border:1px solid #b8c9df; border-radius:5px; background:#eef4fb; color:#244e7b; font-size:16px; font-weight:750; font-variant-numeric:tabular-nums; }

.chart-card__badges span {
  display: inline-flex;
  align-items: center;
  min-height: 19px;
  padding: 2px 6px;
  overflow: hidden;
  border: 1px solid var(--vv-border, #dbe3ee);
  border-radius: 6px;
  background: var(--vv-muted-surface, #f7f9fc);
  color: var(--vv-muted, #526174);
  font-size: clamp(10px, 0.32vw, 12px);
  font-weight: 700;
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.highlight-badge {
  max-width: 200px;
  border-color: #f4c85c !important;
  background: #fffbeb !important;
  color: #92400e !important;
}

.chart-card h2 {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--vv-text, #1f2937);
  font-size: clamp(16px, 0.5vw, 20px);
  font-weight: 680;
  line-height: 1.35;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.chart-card__meta {
  margin: 5px 0 0;
  color: var(--vv-muted, #657386);
  font-size: clamp(11px, 0.34vw, 13px);
  line-height: 1.4;
}

.chart-card__info { flex:0 0 auto; }
.chart-card__info summary { display:flex; align-items:center; justify-content:center; width:28px; height:28px; border-radius:6px; color:var(--vv-muted, #526174); cursor:pointer; list-style:none; font-size:18px; }
.chart-card__info summary::-webkit-details-marker { display:none; }
.chart-card__info summary:hover,.chart-card__info[open] summary { background:var(--vv-muted-surface, #f7f9fc); color:var(--vv-accent, #2563eb); }
.chart-card__info summary:focus-visible,.heatmap-pages button:focus-visible { outline:2px solid var(--vv-accent, #2563eb); outline-offset:2px; }
.chart-card__info-panel { position:absolute; top:30px; right:0; z-index:5; width:min(320px, 100%); padding:12px; border:1px solid var(--vv-border, #dbe3ee); border-radius:8px; background:var(--vv-surface, #fff); box-shadow:0 4px 16px #0f172a1a; font-size:12px; line-height:1.5; overflow-wrap:anywhere; }
.chart-card__info-panel p { margin:4px 0 0; }

.heatmap-pages { display:flex; align-items:center; justify-content:flex-end; flex-wrap:wrap; gap:4px 10px; margin:0 0 6px; color:var(--vv-muted, #526174); font-size:clamp(11px, 0.34vw, 13px); }
.heatmap-pages__status,.heatmap-pages__actions { display:flex; align-items:center; justify-content:flex-end; flex-wrap:wrap; gap:4px; }
.heatmap-pages__status strong { color:var(--vv-text, #334155); font-weight:650; }
.heatmap-pages__notice { color:#9a6700; }
.heatmap-pages button { min-width:28px; min-height:28px; padding:3px 8px; border:1px solid var(--vv-border, #cbd5e1); border-radius:6px; background:var(--vv-surface, #fff); color:var(--vv-text, #334155); font:inherit; font-weight:600; cursor:pointer; }
.heatmap-pages button:disabled { cursor:not-allowed; opacity:.45; }
.heatmap-pages button:hover:not(:disabled) { border-color:var(--vv-accent, #2563eb); color:var(--vv-accent, #1d4ed8); }
.heatmap-pages button[aria-pressed="true"] { border-color:var(--vv-accent, #2563eb); background:#eff6ff; color:var(--vv-accent, #1d4ed8); }

.analysis-notices { margin:0 0 12px; padding:8px 10px; border:1px solid #e6c766; border-radius:8px; background:#fff9e8; color:#78550a; font-size:clamp(11px, 0.34vw, 13px); }
.analysis-notices summary { cursor:pointer; font-weight:700; }
.analysis-notices ul { margin:6px 0 0; padding-left:18px; }

@media (max-width: 560px) {
  .chart-card__header { grid-template-columns: minmax(0,1fr); }
  .chart-card__badges { justify-content:flex-start; }
  .chart-card h2 { grid-column:1; }
}

.chart-card__body {
  flex: 0 0 auto;
  width: 100%;
  min-width: 0;
  overflow: auto;
}

.chart-card[data-bounded="true"] .chart-card__body { flex:1 1 0; min-height:0; overflow:clip; }

.chart-card__body :deep(.vega-embed) {
  display:block;
  width: 100%;
  min-width: var(--plot-min-width, 0);
  max-width: 100%;
}

.chart-card__body :deep(svg) {
  display: block;
  max-width: none;
}
</style>
