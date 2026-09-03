import { useCallback, useState } from "react";
import { useToast } from "../components/ui/Toast";
import type { Tone } from "../lib/status";
import { errMessage } from "../lib/errors";

interface UseActionOptions {
  /** SEMPRE usada no lugar de `r.message` — para quando a mensagem do
   *  backend é genérica e o chamador tem algo mais específico (ex.:
   *  "Parada solicitada para <id>" em vez do texto cru da API). */
  overrideMessage?: string;
  /** Usada só quando `r.message` vier vazio — rede de segurança, não
   *  substituição (ex.: "<nome> pausada" se a API não mandar mensagem). */
  fallbackMessage?: string;
  /** Tom do toast de sucesso — "cyan" por padrão; algumas ações usam "amber"
   *  para sinalizar atenção (ex.: parar uma execução) em vez de rotina. */
  successTone?: Tone;
  /** Roda depois do sucesso — tipicamente `refresh`/`reload` do `usePolling`
   *  da tela, ou `Promise.all` de vários (o valor de retorno é ignorado). */
  onDone?: () => unknown | Promise<unknown>;
}

/** Padrão `busy -> try -> await -> toast de sucesso -> catch -> toast de
 *  erro -> finally -> onDone` — estava reimplementado 5 vezes no app
 *  (AutomacoesPage, SystemPage, ExecucoesPage ×2, BeneficiamentoPage), cada
 *  cópia divergindo um pouco em nome de variável e ordem (achado nº 17,
 *  Onda 4). `key` identifica a ação em andamento — id numérico de uma
 *  automação/execução, ou uma string fixa ("refresh", "purge") quando a
 *  tela só tem uma ação por vez. */
export function useAction<K extends string | number = string>() {
  const toast = useToast();
  const [busyKey, setBusyKey] = useState<K | null>(null);

  const run = useCallback(
    async (key: K, fn: () => Promise<{ message: string } | void>, opts?: UseActionOptions) => {
      setBusyKey(key);
      try {
        const r = await fn();
        const backendMsg = r && "message" in r ? r.message : undefined;
        // `||`, não `??`: uma API que devolve `message: ""` deve cair no
        // fallback tanto quanto uma que não devolve `message` nenhum.
        const msg = opts?.overrideMessage ?? (backendMsg || opts?.fallbackMessage);
        if (msg) toast(msg, opts?.successTone ?? "cyan");
        await opts?.onDone?.();
      } catch (e) {
        toast(errMessage(e), "red");
      } finally {
        setBusyKey(null);
      }
    },
    [toast],
  );

  return { busyKey, isBusy: (key: K) => busyKey === key, run };
}
