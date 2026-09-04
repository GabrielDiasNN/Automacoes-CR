import { lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ApiKeyProvider } from "./context/ApiKeyContext";
import { LiveStatusProvider } from "./context/LiveStatusContext";
import { TableDensityProvider } from "./context/TableDensityContext";
import { ThemeProvider } from "./context/ThemeContext";
import { ApiKeyGate } from "./components/ApiKeyGate";
import { ToastProvider } from "./components/ui";
import { Shell } from "./components/Shell";
import { PainelPage } from "./pages/PainelPage";
import { ExecucoesPage } from "./pages/ExecucoesPage";
import { AutomacoesPage } from "./pages/AutomacoesPage";
import { NotFoundPage } from "./pages/NotFoundPage";

// Code-splitting: as três páginas que carregam uPlot (TimeSeries) e os
// painéis mais pesados (Beneficiamento: Treemap + FilterBar + drill-down;
// Monitor: console ao vivo; Sistema: gauges) saem do bundle inicial — quem
// abre /painel não precisa baixá-las (achado nº 6, Onda 5). `Shell.tsx`
// envolve o `<Outlet/>` num `<Suspense>` com fallback de `Loading`.
const MonitorPage = lazy(() => import("./pages/MonitorPage").then((m) => ({ default: m.MonitorPage })));
const BeneficiamentoPage = lazy(() =>
  import("./pages/BeneficiamentoPage").then((m) => ({ default: m.BeneficiamentoPage })),
);
const SystemPage = lazy(() => import("./pages/SystemPage").then((m) => ({ default: m.SystemPage })));

export default function App() {
  return (
    <ThemeProvider>
      <ApiKeyProvider>
        <ToastProvider>
          <TableDensityProvider>
            <ApiKeyGate>
              <BrowserRouter basename="/dashboard">
                <Routes>
                  <Route
                    element={
                      <LiveStatusProvider>
                        <Shell />
                      </LiveStatusProvider>
                    }
                  >
                    <Route index element={<Navigate to="/painel" replace />} />
                    <Route path="painel" element={<PainelPage />} />
                    <Route path="execucoes" element={<ExecucoesPage />} />
                    <Route path="monitor" element={<MonitorPage />} />
                    <Route path="observabilidade" element={<Navigate to="/monitor" replace />} />
                    <Route path="beneficiamento" element={<BeneficiamentoPage />} />
                    <Route path="automacoes" element={<AutomacoesPage />} />
                    <Route path="sistema" element={<SystemPage />} />
                    <Route path="*" element={<NotFoundPage />} />
                  </Route>
                </Routes>
              </BrowserRouter>
            </ApiKeyGate>
          </TableDensityProvider>
        </ToastProvider>
      </ApiKeyProvider>
    </ThemeProvider>
  );
}
