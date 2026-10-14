import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const devApiTarget = process.env.DEV_API_PROXY_TARGET || "https://localhost:7242";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": devApiTarget,
      "/auth": devApiTarget,
    },
  },
  preview: { port: 5173 },
});
