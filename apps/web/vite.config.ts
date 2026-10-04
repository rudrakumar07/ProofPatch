import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies to the FastAPI backend so the frontend can use relative
// URLs in both development and production.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
  },
});
