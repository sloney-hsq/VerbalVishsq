<template>
  <div v-if="error" class="preview-error" role="alert"><h1>Unable to load saved results</h1><p>{{ error }}</p></div>
  <Dashboard v-else preview-mode />
</template>

<script setup>
import { onMounted, ref } from 'vue';
import Dashboard from './Dashboard.vue';
import { useDashboardStore } from '../stores/dashboard';

const error = ref('');
const store = useDashboardStore();
const titles = {
  delivery_rank: 'Where are deliveries most often late?',
  delivery_monthly: 'Delivery risk over time',
  delivery_box: 'The spread of delivery times',
  delivery_heatmap: 'Delivery risk across product categories',
  rating_composition: 'How customers rate their orders',
  freight_rank: 'Freight burden by product category',
  freight_histogram: 'The distribution of freight costs',
  freight_scatter: 'Product price and freight cost',
  freight_bins: 'Where price and freight observations cluster',
  regional_delivery_risk: 'Delivery performance by state',
  delivery_period_change: 'Delivery performance over time',
  low_rating_delivery: 'Review scores and delivery time',
  freight_robustness: 'Freight burden by category',
  freight_attribute_association: 'Product weight and freight cost',
  seller_delivery_stability: 'Seller delivery consistency',
};
const columns = { group: { type: 'nominal', label: 'Group' }, value: { type: 'quantitative', label: 'Value', unit: 'count' } };
onMounted(async () => {
  try {
    const response = await fetch('/__visual-check-data');
    if (!response.ok) throw new Error(`Saved chart request failed (${response.status}). Generate the visual-check data or configure VERBALVIS_VISUAL_CHECK_MANIFEST.`);
    const views = Object.values(await response.json()).map(view => ({ ...view, title: titles[view.title] || view.title }));
    if (new URLSearchParams(window.location.search).get('debug') === '1') {
      views.push({ id: 'edge-long-title', title: 'Synthetic layout check · a long analytical title that should wrap without hiding chart metadata', chart_type: 'bar', result_kind: 'aggregate', data: [{ group: 'Alpha', value: 4 }, { group: 'Beta', value: 7 }], columns, visual: { type: 'bar', encoding: { x: 'group', y: 'value' } } });
      views.push({ id: 'edge-three-facets', title: 'Synthetic layout check · three panels with independent scales', chart_type: 'bar', result_kind: 'aggregate', data: ['One', 'Two', 'Three'].flatMap((panel, index) => [{ panel, group: 'A', value: index + 1 }, { panel, group: 'B', value: (index + 1) * 10 }]), columns: { ...columns, panel: { type: 'nominal', label: 'Panel' } }, visual: { type: 'bar', encoding: { x: 'group', y: 'value', facet: 'panel' }, scales: { resolve: 'independent' } } });
      views.push({ id: 'edge-long-horizontal-bar', title: 'Synthetic layout check · fifty-five categories', chart_type: 'bar', result_kind: 'aggregate', data: Array.from({ length: 55 }, (_, index) => ({ group: `Category ${index + 1}`, value: 55 - index })), columns, visual: { type: 'bar', encoding: { x: 'value', y: 'group' } } });
    }
    store.initViews(views, 1, { filters: [] });
  } catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason); }
});
</script>

<style scoped>
.preview-error { padding: 40px; font: 16px/1.7 'Segoe UI', sans-serif; color: #7d3d37; }
.preview-error h1 { font-size: 24px; }
</style>
