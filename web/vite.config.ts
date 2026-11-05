import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  // VITE_API_TARGET comes from the environment (docker: http://api:8000) or from
  // web/.env.local (e.g. http://localhost:8001 when API_PORT is changed in the root .env).
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_API_TARGET || "http://localhost:8000";

  return {
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
  };
});
