import { useLocation, useNavigate } from "react-router-dom";
import { Compass } from "lucide-react";
import { Button, EmptyState, Nameplate } from "../components/ui";
import page from "./page.module.css";

/** Rota inexistente. Antes redirecionava em silêncio para /painel (achado
 *  nº 6, Onda 1) — uma URL colada errada, ou um link quebrado do Ctrl+K,
 *  nunca avisava que o caminho não existia. */
export function NotFoundPage() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className={page.page}>
      <Nameplate eyebrow="// erro" title="Página não encontrada" />
      <EmptyState
        icon={<Compass size={28} />}
        title={`Não existe rota para "${location.pathname}"`}
        hint="Confira o link ou use a busca global (Ctrl+K) para encontrar a tela certa."
      />
      <div>
        <Button onClick={() => navigate("/painel")}>Ir para o Painel</Button>
      </div>
    </div>
  );
}
