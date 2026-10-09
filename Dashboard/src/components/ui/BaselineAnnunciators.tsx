import { healthLabel, healthTone } from "../../lib/status";
import { Annunciator, AnnunciatorGrid } from "./Annunciator";

/** Forma mínima de uma métrica do baseline operacional (`BaselineMetric` do
 *  backend). Tipada estrutural para a camada `ui` não depender de `api/`. */
interface BaselineMetricLike {
  code: string;
  label: string;
  status: string;
  current_value: string | null;
}

/** Grade de anunciadores do baseline operacional, usada por Painel e Sistema.
 *  Tom e rótulo saem de `healthTone`/`healthLabel`: o mesmo vocabulário de
 *  saúde (healthy | attention | incident) que o backend envia. */
export function BaselineAnnunciators({ metrics }: { metrics: readonly BaselineMetricLike[] }) {
  return (
    <AnnunciatorGrid>
      {metrics.map((m) => (
        <Annunciator
          key={m.code}
          legend={m.label}
          value={m.current_value ?? undefined}
          tone={healthTone(m.status)}
          active={m.status !== "healthy"}
          blink={m.status === "incident"}
          statusLabel={healthLabel(m.status)}
        />
      ))}
    </AnnunciatorGrid>
  );
}
