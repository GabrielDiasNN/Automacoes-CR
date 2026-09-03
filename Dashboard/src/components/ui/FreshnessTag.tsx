import { formatAge } from "../../lib/format";
import { StatusTag } from "./StatusTag";

interface FreshnessTagProps {
  /** `lastUpdated` de `usePolling` — hora do último dado que chegou com sucesso. */
  lastUpdated: Date | null;
  /** `error` de `usePolling`. Quando definido AO MESMO TEMPO que já há dados em
   *  tela, o polling está falhando silenciosamente por baixo de números que
   *  parecem ao vivo — este é o componente que torna essa falha visível
   *  (achado nº 2, Onda 1: "falso-verde do polling"). */
  error: string | null;
  /** `rateLimitedUntil` de `usePolling`, quando disponível — mensagem própria
   *  em vez de "desatualizado há Xm" (a causa é conhecida e é temporária). */
  rateLimitedUntil?: Date | null;
}

/** Mostra o horário do último dado válido e, quando o polling está falhando
 *  com dados em tela, avisa em vez de deixar a tela parecer atualizada. */
export function FreshnessTag({ lastUpdated, error, rateLimitedUntil }: FreshnessTagProps) {
  if (error && rateLimitedUntil) {
    return (
      <StatusTag tone="amber" dot>
        {error}
      </StatusTag>
    );
  }
  if (error) {
    const ageSeconds = lastUpdated ? (Date.now() - lastUpdated.getTime()) / 1000 : null;
    return (
      <StatusTag tone="amber" dot>
        {lastUpdated ? `dados desatualizados há ${formatAge(ageSeconds)}` : "sem dados — falha na conexão"}
      </StatusTag>
    );
  }
  if (!lastUpdated) return null;
  return <span className="label-mono">{lastUpdated.toLocaleTimeString("pt-BR")}</span>;
}
