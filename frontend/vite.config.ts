import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// prévia pública: fora dos buscadores
const semIndexacao: Plugin = {
  name: "rastro-previa-noindex",
  transformIndexHtml: (html) =>
    process.env.VITE_PREVIA === "1"
      ? html.replace("<head>", '<head>\n    <meta name="robots" content="noindex" />')
      : html,
};

export default defineConfig({
  plugins: [react(), semIndexacao],
  // no GitHub Pages o site fica em /rastro-publico/ (VITE_BASE=/rastro-publico/)
  base: process.env.VITE_BASE ?? "/",
  server: {
    // em desenvolvimento, /api (só auditoria) vai para o backend local
    proxy: { "/api": "http://localhost:8000" },
  },
});
