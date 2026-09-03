import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/dashboard/",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // Alinhado ao `target` do tsconfig.json (ES2020). Explicito para o build
    // nao seguir o default do Vite, que muda entre versoes.
    target: "es2020",
    // Gera .map mas sem o comentario `//# sourceMappingURL` nos .js servidos —
    // erro reportado por operador fica depuravel sem expor o mapa em producao.
    sourcemap: "hidden",
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        // Vendors com ciclo de vida proprio saem do chunk inicial e dos chunks
        // de pagina: react/router (base), uplot (so Monitor/Sistema/Beneficiamento)
        // e lucide (compartilhado por telas estaticas e lazy).
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          uplot: ["uplot"],
          lucide: ["lucide-react"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
});
