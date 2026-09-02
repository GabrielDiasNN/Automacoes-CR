import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ApiKeyProvider } from "./context/ApiKeyContext";
import { LiveStatusProvider } from "./context/LiveStatusContext";
import { TableDensityProvider } from "./context/TableDensityContext";
import { ApiKeyGate } from "./components/ApiKeyGate";
import { ToastProvider } from "./components/ui";
import { Shell } from "./components/Shell";
import { PainelPage } from "./pages/PainelPage";
import { ExecucoesPage } from "./pages/ExecucoesPage";
import { MonitorPage } from "./pages/MonitorPage";
import { BeneficiamentoPage } from "./pages/BeneficiamentoPage";
import { AutomacoesPage } from "./pages/AutomacoesPage";
import { SystemPage } from "./pages/SystemPage";
import { NotFoundPage } from "./pages/NotFoundPage";

export default function App() {
  return (
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
  );
}
