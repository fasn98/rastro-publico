import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // em desenvolvimento, /api vai para o backend FastAPI
    proxy: { "/api": "http://localhost:8000" },
  },
});
