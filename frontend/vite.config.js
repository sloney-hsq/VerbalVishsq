import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

function visualCheckFixture() {
  return {
    name:"verbalvis-visual-check-fixture",
    configureServer(server) {
      server.middlewares.use('/__visual-check-data', async (_request,response) => {
        const configured = process.env.VERBALVIS_VISUAL_CHECK_MANIFEST;
        const fixture = resolve(process.cwd(),configured || '../.superpowers/sdd/2026-10-16-study-tools-and-chart-layout/visual-check/views.json');
        try {
          response.setHeader('Content-Type','application/json; charset=utf-8');
          response.end(await readFile(fixture,'utf8'));
        } catch (error) {
          response.statusCode = 404;
          response.end(JSON.stringify({error:`Unable to read visual-check fixture: ${error.message}`}));
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [vue(),visualCheckFixture()],
  server: {
    port: 5174,
    proxy: {
      "/ws": {
        target: "ws://127.0.0.1:8001",
        ws: true,
      },
      "/api": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
      },
    },
  },
});
