import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": "http://api:8000",
      "/bank": {
        target: "http://bank:8001",
        rewrite: (path) => path.replace(/^\/bank/, ""),
      },
    },
  },
  test: { environment: "jsdom", globals: true },
});
