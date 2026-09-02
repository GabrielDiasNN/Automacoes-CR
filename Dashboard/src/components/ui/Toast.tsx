import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { toneTint, toneVar, type Tone } from "../../lib/status";
import styles from "./Toast.module.css";

interface ToastItem {
  id: number;
  tone: Tone;
  message: string;
}

interface ToastApi {
  push: (message: string, tone?: Tone) => void;
}

const ToastCtx = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const idRef = useRef(0);

  const push = useCallback((message: string, tone: Tone = "cyan") => {
    const id = (idRef.current += 1);
    setItems((prev) => [...prev, { id, tone, message }]);
    setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), 4200);
  }, []);

  return (
    <ToastCtx.Provider value={{ push }}>
      {children}
      <div className={styles.wrap} role="status" aria-live="polite">
        {items.map((t) => (
          <div
            key={t.id}
            className={`${styles.toast} animate-in`}
            // Erro (tom vermelho) é assertivo: `role="alert"` sobrepõe o
            // `aria-live="polite"` do container para essa mensagem — antes
            // o erro de uma ação destrutiva (ex.: falha ao Parar uma
            // execução) tinha a mesma prioridade de anúncio que um "ok".
            role={t.tone === "red" ? "alert" : undefined}
            style={{ borderColor: toneVar[t.tone], background: toneTint[t.tone] }}
          >
            <span className={styles.bar} style={{ background: toneVar[t.tone] }} />
            {t.message}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast(): ToastApi["push"] {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast precisa de <ToastProvider>");
  return ctx.push;
}
