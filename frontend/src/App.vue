<template>
  <Dashboard />
</template>

<script setup>
import Dashboard from "./components/Dashboard.vue";
</script>

<style>
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html,
body,
#app {
  width: 100%;
  height: 100%;
  min-height: 100%;
  overflow: hidden;
}

body {
  background: #f7f9fc;
}
</style>
