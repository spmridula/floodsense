import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const backend = process.env.FLOODSENSE_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": backend, "/health": backend, "/ready": backend } },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test/setup.ts"] },
});
