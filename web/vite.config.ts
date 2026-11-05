import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In docker the web container sets VITE_API_TARGET=http://api:8000.
const target = process.env.VITE_API_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  define: {
    __BUILD_DATE__: JSON.stringify(new Date().toISOString()),
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target, changeOrigin: true },
      "/media": { target, changeOrigin: true },
    },
  },
});
