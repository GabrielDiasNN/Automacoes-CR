import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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

const DISMISS_MS = 4200;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const idRef = useRef(0);
  // Um timer por toast — permite pausar/retomar individualmente (hover).
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const scheduleRemoval = useCallback((id: number) => {
    const handle = setTimeout(() => {
      timersRef.current.delete(id);
      setItems((prev) => prev.filter((t) => t.id !== id));
    }, DISMISS_MS);
    timersRef.current.set(id, handle);
  }, []);

  const push = useCallback(
    (message: string, tone: Tone = "cyan") => {
      const id = (idRef.current += 1);
      setItems((prev) => [...prev, { id, tone, message }]);
      scheduleRemoval(id);
    },
    [scheduleRemoval],
  );

  // WCAG 2.2.1 (Timing Adjustable): o toast some sozinho em 4,2s — sem pausa,
  // um erro (tom vermelho, ação destrutiva) podia sumir da tela antes do
  // operador terminar de ler. Hover cancela o timer; sair reagenda do zero.
  const pause = useCallback((id: number) => {
    const handle = timersRef.current.get(id);
    if (handle) {
      clearTimeout(handle);
      timersRef.current.delete(id);
    }
  }, []);
  const resume = useCallback(
    (id: number) => {
      if (!timersRef.current.has(id)) scheduleRemoval(id);
    },
    [scheduleRemoval],
  );

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      for (const handle of timers.values()) clearTimeout(handle);
      timers.clear();
    };
  }, []);

  // ToastProvider está acima do router (App.tsx) — sem useMemo, `value` era
  // um objeto novo a cada render, e como o provider re-renderiza a cada
  // toast (push, e de novo 4,2s depois na expiração), TODO consumidor de
  // useToast() — páginas inteiras — re-renderizava com ele (achado nº 30,
  // Onda 5).
  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastCtx.Provider value={value}>
      {children}
      {/* Sem `role="status"` no wrapper: um filho com `role="alert"` (erro)
       *  precisa da própria região ao vivo — aninhar `alert` dentro de
       *  `status` produzia leitura duplicada/confusa em alguns leitores de
       *  tela. `aria-live="polite"` sozinho já cobre os toasts normais. */}
      <div className={styles.wrap} aria-live="polite">
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
            onMouseEnter={() => pause(t.id)}
            onMouseLeave={() => resume(t.id)}
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
