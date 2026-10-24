import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: {
    sourcemap: true,
    // maplibre-gl is ~800 kB on its own and already isolated in a cacheable vendor chunk.
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: { manualChunks: { maplibre: ["maplibre-gl"] } },
    },
  },
});
