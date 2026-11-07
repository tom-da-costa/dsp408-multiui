import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vitest/config";

const backend = process.env.DSP408_BACKEND ?? "http://127.0.0.1:8080";

export default defineConfig({
  plugins: [svelte()],
  build: {
    // The built UI is committed inside the Python package (SPEC D9).
    outDir: "../src/dsp408_multiui/web",
    emptyOutDir: true,
    target: "es2022",
    assetsInlineLimit: 0,
  },
  server: {
    proxy: {
      "/api": backend,
      "/ws": { target: backend.replace(/^http/, "ws"), ws: true },
    },
  },
  test: {
    include: ["src/**/*.test.ts"],
  },
});
