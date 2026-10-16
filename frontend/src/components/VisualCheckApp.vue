<template>
  <main class="check-shell">
    <section>
      <p v-if="error" role="alert">{{ error }}</p>
      <div ref="grid" v-chart-grid class="chart-grid">
        <ChartSlot v-for="view in views" :key="view.id" :view="view" :available-width="width" />
      </div>
      <details v-if="showDebug" class="edge-cases">
        <summary>Local synthetic edge cases</summary>
        <p>Layout-only fixtures: long title, null values, three facets, and a long horizontal bar.</p>
        <div v-chart-grid class="chart-grid">
          <ChartSlot v-for="view in edgeViews" :key="view.id" :view="view" :available-width="width" />
        </div>
      </details>
    </section>
  </main>
</template>

<script setup>
import {onBeforeUnmount,onMounted,ref} from 'vue';
import ChartSlot from './ChartSlot.vue';
import {vChartGrid} from '../chartGrid.js';

const views = ref([]);
const error = ref('');
const grid = ref(null);
const width = ref(0);
let observer;
const showDebug = new URLSearchParams(window.location.search).get('debug') === '1';
const exampleTitles = {
  regional_delivery_risk:'Delivery performance by state',
  delivery_period_change:'Delivery performance over time',
  low_rating_delivery:'Review scores and delivery time',
  freight_robustness:'Freight burden by category',
  freight_attribute_association:'Product weight and freight cost',
  seller_delivery_stability:'Seller delivery consistency',
};
const baseColumns = {group:{type:'nominal',label:'Group'},value:{type:'quantitative',label:'Value',unit:'count'}};
const edgeViews = [
  {id:'edge-long-title',title:'A deliberately long analytical title that wraps across two lines without hiding metadata badges',chart_type:'bar',result_kind:'aggregate',data:[{group:'Alpha',value:4},{group:'Beta',value:7}],columns:baseColumns,visual:{type:'bar',encoding:{x:'group',y:'value'}}},
  {id:'edge-null-values',title:'Null value handling',chart_type:'scatter',result_kind:'points',data:[{x:1,y:2},{x:2,y:null},{x:null,y:4}],columns:{x:{type:'quantitative'},y:{type:'quantitative'}},visual:{type:'scatter',encoding:{x:'x',y:'y'}}},
  {id:'edge-three-facets',title:'Three facets with independent scales',chart_type:'bar',result_kind:'aggregate',data:['One','Two','Three'].flatMap((panel,index) => [{panel,group:'A',value:index + 1},{panel,group:'B',value:(index + 1) * 10}]),columns:{...baseColumns,panel:{type:'nominal',label:'Panel'}},visual:{type:'bar',encoding:{x:'group',y:'value',facet:'panel'},scales:{resolve:'independent'}}},
  {id:'edge-long-horizontal-bar',title:'Fifty-five categories remain readable',chart_type:'bar',result_kind:'aggregate',data:Array.from({length:55},(_,index) => ({group:`Category ${index + 1}`,value:55 - index})),columns:baseColumns,visual:{type:'bar',encoding:{x:'value',y:'group'}}},
];

onMounted(async () => {
  try {
    const response = await fetch('/__visual-check-data');
    if (!response.ok) throw new Error(`Fixture request failed (${response.status})`);
    views.value = Object.values(await response.json()).map(view => ({
      ...view, title: exampleTitles[view.title] || view.title,
    }));
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  }
  observer = new ResizeObserver(entries => {width.value = Math.round(entries[0]?.contentRect?.width || 0);});
  if (grid.value) observer.observe(grid.value);
});

onBeforeUnmount(() => observer?.disconnect());
</script>

<style scoped>
.check-shell { width:100%; max-width:1600px; margin:0 auto; min-height:100vh; padding:24px; }
section { min-width:0; }
.edge-cases { margin-top:16px; padding:12px; border:1px dashed #94a3b8; border-radius:12px; background:#eef2f7; }
.edge-cases summary { cursor:pointer; font-weight:700; }
@media(max-width:700px) { .check-shell { padding:12px; } }
</style>
