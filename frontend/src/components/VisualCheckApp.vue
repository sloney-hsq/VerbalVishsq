<template>
  <main class="check-shell">
    <aside>
      <strong>Component layout check</strong>
      <p>Production ChartSlot components with a measured dashboard container. No provider, WebSocket, microphone, or simulated voice session.</p>
      <p>{{ views.length }} exported views</p>
    </aside>
    <section>
      <p v-if="error" role="alert">{{ error }}</p>
      <div ref="grid" class="chart-grid">
        <ChartSlot v-for="view in views" :key="view.id" :view="view" :available-width="width" />
      </div>
    </section>
  </main>
</template>

<script setup>
import {onBeforeUnmount,onMounted,ref} from 'vue';
import ChartSlot from './ChartSlot.vue';

const views = ref([]);
const error = ref('');
const grid = ref(null);
const width = ref(0);
let observer;

onMounted(async () => {
  try {
    const response = await fetch('/__visual-check-data');
    if (!response.ok) throw new Error(`Fixture request failed (${response.status})`);
    views.value = Object.values(await response.json());
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  }
  observer = new ResizeObserver(entries => {width.value = Math.round(entries[0]?.contentRect?.width || 0);});
  if (grid.value) observer.observe(grid.value);
});

onBeforeUnmount(() => observer?.disconnect());
</script>

<style scoped>
.check-shell { display:grid; grid-template-columns:240px minmax(0,1fr); gap:16px; min-height:100vh; padding:16px; }
aside { padding:16px; border:1px solid #d9e1ec; border-radius:12px; background:#fff; }
section { min-width:0; }
@media(max-width:700px) { .check-shell { grid-template-columns:1fr; padding:8px; } aside { display:none; } }
</style>
