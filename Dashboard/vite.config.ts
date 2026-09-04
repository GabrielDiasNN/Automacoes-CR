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
    // Omite o comentario `//# sourceMappingURL` dos .js servidos, mas o arquivo
    // `.map` continua sendo emitido em dist/ e e servido publicamente.
    sourcemap: "hidden",
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        // Vendors com ciclo de vida proprio saem do chunk inicial e dos chunks
        // de pagina: react/router (base), uplot (so Monitor/Sistema/Beneficiamento)
        // e lucide (compartilhado por telas estaticas e lazy).
        //
        // Forma de FUNCAO: o Vite 8 usa rolldown, que so aceita manualChunks
        // como funcao (a forma de objeto quebra o build).
        manualChunks(id) {
          const p = id.replace(/\\/g, "/");
          if (!p.includes("/node_modules/")) return undefined;
          if (p.includes("/node_modules/uplot/")) return "uplot";
          if (p.includes("/node_modules/lucide-react/")) return "lucide";
          if (/\/node_modules\/(react|react-dom|react-router|react-router-dom|scheduler|@remix-run)\//.test(p)) {
            return "react";
          }
          return undefined;
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
