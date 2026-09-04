import { useState } from "react";
import { useApiKeyContext } from "../context/ApiKeyContext";
import { Button } from "./ui";
import styles from "./ApiKeyGate.module.css";

export function ApiKeyGate({ children }: { children: React.ReactNode }) {
  const { hasKey, saveKey } = useApiKeyContext();
  const [input, setInput] = useState("");
  const [error, setError] = useState("");

  if (hasKey) return <>{children}</>;

  const handleSubmit = (e: { preventDefault(): void }) => {
    e.preventDefault();
    const key = input.trim();
    if (!key) {
      setError("Chave não pode estar vazia.");
      return;
    }
    saveKey(key);
  };

  return (
    <div className={styles.page}>
      <div className={`hazard ${styles.rail}`} aria-hidden="true" />
      <div className={styles.center}>
        <form onSubmit={handleSubmit} className={styles.form}>
          <div>
            <div className={styles.brand}>ORQUESTRADOR</div>
            <div className={styles.subtitle}>// autenticação zero-trust</div>
          </div>

          <div className={styles.divider} />

          <p className={styles.hint}>Informe a API Key do Orchestrator para acessar a sala de instrumentação.</p>

          <input
            type="password"
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              setError("");
            }}
            placeholder="API Key"
            aria-label="API Key"
            aria-invalid={!!error}
            aria-describedby={error ? "apikey-error" : undefined}
            autoComplete="off"
            // Única tela do app antes de qualquer navegação — não há contexto
            // de leitura em andamento para o autofoco atropelar, e é o padrão
            // esperado num formulário de login de instrumento único.
            // eslint-disable-next-line jsx-a11y/no-autofocus
            autoFocus
            className={[styles.field, error ? styles.fieldError : ""].filter(Boolean).join(" ")}
          />

          {error && (
            <p id="apikey-error" role="alert" className={styles.error}>
              ✗ {error}
            </p>
          )}

          <Button type="submit" variant="primary">
            Entrar →
          </Button>
        </form>
      </div>
    </div>
  );
}
