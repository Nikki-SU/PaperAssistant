import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://tauri.app/v2/guides/getting-started/setup/vite
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1421,
    strictPort: true,
    host: "127.0.0.1",
  },
  envPrefix: ["VITE_", "TAURI_"],
  build: {
    target: "es2020",
    minify: "esbuild",
    sourcemap: true,
  },
});
