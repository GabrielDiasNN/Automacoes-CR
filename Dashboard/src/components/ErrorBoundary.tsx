import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "./ui";
import styles from "./ErrorBoundary.module.css";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/** Rede de segurança contra exceção de render — sem isso, qualquer erro não
 *  tratado (dado inesperado da API, `throw` de contexto fora do provider)
 *  desmonta a árvore inteira e deixa tela branca, sem log visível para o
 *  operador nem caminho de recuperação além de F5 (achado nº 3, Onda 1).
 *
 *  Fica dentro do `<main>` do Shell (ver App.tsx), não em volta dele: rail,
 *  topbar e StatusBar continuam funcionando mesmo se a página atual quebrar.
 *  `key={pathname}` no ponto de uso (App.tsx) remonta o boundary ao trocar
 *  de rota, para que navegar para outra página seja sempre uma via de saída. */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary] exceção não tratada no render:", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className={styles.wrap} role="alert">
        <AlertTriangle size={24} />
        <h2 className={styles.title}>Algo quebrou nesta tela</h2>
        <p className={styles.message}>{error.message || String(error)}</p>
        <Button icon={<RefreshCw size={13} />} onClick={() => window.location.reload()}>
          Recarregar
        </Button>
      </div>
    );
  }
}
