import { useEffect, useRef, useState } from "react";
import { useApiKeyContext } from "../context/ApiKeyContext";
import { Button } from "./ui";
import styles from "./ApiKeyGate.module.css";

export function ApiKeyGate({ children }: { children: React.ReactNode }) {
  const { hasKey, saveKey } = useApiKeyContext();
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Foco no campo ao aparecer (substitui `autoFocus`, que o jsx-a11y veta):
  // esta é a única tela antes da navegação, então o foco inicial é o esperado.
  useEffect(() => {
    if (!hasKey) {
      setInput("");
      inputRef.current?.focus();
    }
  }, [hasKey]);

  if (hasKey) return <>{children}</>;

  const handleSubmit = (e: { preventDefault(): void }) => {
    e.preventDefault();
    const key = input.trim();
    if (!key) {
      setError("Chave não pode estar vazia.");
      return;
    }
    setInput("");
    saveKey(key);
  };

  return (
    <div className={styles.page}>
      <div className={styles.center}>
        <form onSubmit={handleSubmit} className={styles.form}>
          <div>
            <div className={styles.brand}>ORQUESTRADOR</div>
            <div className={styles.subtitle}>Acesso autenticado</div>
          </div>

          <div className={styles.divider} />

          <p className={styles.hint}>Informe a API Key para acessar o painel de operações e consultas.</p>

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
            ref={inputRef}
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
