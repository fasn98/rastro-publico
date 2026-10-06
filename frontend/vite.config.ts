import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // no GitHub Pages o site fica em /rastro-publico/ (VITE_BASE=/rastro-publico/)
  base: process.env.VITE_BASE ?? "/",
  server: {
    // em desenvolvimento, /api (só auditoria) vai para o backend local
    proxy: { "/api": "http://localhost:8000" },
  },
});
