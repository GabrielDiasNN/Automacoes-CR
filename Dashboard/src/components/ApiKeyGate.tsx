import { useState } from "react";
import { useApiKeyContext } from "../context/ApiKeyContext";
import { Button } from "./ui";

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
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "var(--bg)" }}>
      <div className="hazard" style={{ height: "var(--brand-rail-h)", flexShrink: 0 }} aria-hidden="true" />
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "var(--sp-4)" }}>
        <form
          onSubmit={handleSubmit}
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-lg)",
            boxShadow: "var(--shadow-2)",
            padding: "var(--sp-6) var(--sp-5)",
            width: 360,
            maxWidth: "100%",
            display: "flex",
            flexDirection: "column",
            gap: "var(--sp-4)",
          }}
        >
          <div>
            <div
              style={{
                fontFamily: "var(--font-display)",
                fontWeight: 700,
                fontSize: "1.05rem",
                color: "var(--cyan)",
                letterSpacing: "0.16em",
                textTransform: "uppercase",
              }}
            >
              ORQUESTRADOR
            </div>
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--fs-label)",
                color: "var(--text-lo)",
                marginTop: 6,
                letterSpacing: "var(--track-mid)",
              }}
            >
              // autenticação zero-trust
            </div>
          </div>

          <div style={{ height: 1, background: "var(--border)", margin: "0 calc(-1 * var(--sp-5))" }} />

          <p style={{ margin: 0, color: "var(--text-mid)", fontSize: "var(--fs-small)", lineHeight: "var(--lh-normal)" }}>
            Informe a API Key do Orchestrator para acessar a sala de instrumentação.
          </p>

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
            style={{
              padding: "0.65rem 0.8rem",
              border: `1px solid ${error ? "var(--red)" : "var(--border)"}`,
              borderRadius: "var(--radius)",
              background: "var(--bg)",
              color: "var(--text-hi)",
              fontSize: "var(--fs-body)",
              fontFamily: "var(--font-mono)",
              outline: "none",
            }}
          />

          {error && (
            <p
              id="apikey-error"
              role="alert"
              style={{ margin: 0, color: "var(--red)", fontSize: "var(--fs-small)", fontFamily: "var(--font-mono)" }}
            >
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
