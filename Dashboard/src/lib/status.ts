/** Mapeamento central status/severidade → tom de cor + rótulo.
 *  Fonte única de verdade (antes espalhado em cada página). */

import type { ExecutionStatus, SlaState } from "../api/orchestrator";

export type Tone = "cyan" | "amber" | "green" | "red" | "blue" | "grey";

export const toneVar: Record<Tone, string> = {
  cyan: "var(--cyan)",
  amber: "var(--amber)",
  green: "var(--green)",
  red: "var(--red)",
  blue: "var(--blue)",
  grey: "var(--grey)",
};

export const toneTint: Record<Tone, string> = {
  cyan: "var(--cyan-tint)",
  amber: "var(--amber-tint)",
  green: "var(--green-tint)",
  red: "var(--red-tint)",
  blue: "var(--blue-tint)",
  grey: "var(--grey-tint)",
};

/** Cor do halo de `animation: pulse-ring` (StatusTag/Annunciator com `pulse`).
 *  Sem isso o keyframe usava --amber-glow fixo: um StatusTag vermelho com
 *  `pulse` pulsava âmbar, dessincronizado do próprio tom que estava exibindo. */
export const toneGlow: Record<Tone, string> = {
  cyan: "var(--cyan-glow)",
  amber: "var(--amber-glow)",
  green: "var(--green-glow)",
  red: "var(--red-glow)",
  blue: "var(--blue-glow)",
  grey: "var(--grey-glow)",
};

/** Estado de execução → tom. */
export function executionTone(status: ExecutionStatus): Tone {
  switch (status?.toUpperCase()) {
    case "SUCCESS":
      return "green";
    case "ERROR":
    case "TIMEOUT":
    case "FAILED_BY_REBOOT":
      return "red";
    case "RUNNING":
    case "CLAIMED": // não existe no backend (ver comentário em orchestrator.ts); tolerado por segurança
      return "amber";
    case "PENDING":
      return "cyan";
    case "EXPIRED":
      // Slot agendado não entregue (descartado por teto de fila), não erro de
      // execução — tom próprio para não se confundir com ERROR/TIMEOUT (red).
      return "blue";
    default:
      return "grey"; // TERMINATED, REQUEUED, PARTIAL
  }
}

/** Severidade do operador → tom. */
export function severityTone(severity: string | null | undefined): Tone {
  switch (severity?.toUpperCase()) {
    case "CRITICAL":
      return "red";
    case "HIGH":
      return "amber";
    case "MODERATE":
      return "cyan";
    default:
      return "grey";
  }
}

/** Saúde de sistema / baseline → tom.
 *  Cobre 3 vocabulários que compartilham a função por semântica equivalente:
 *  - `SystemHealth`/`SystemLiveness` (backend): healthy|ok | degraded | unhealthy
 *  - baseline operacional (backend): healthy | attention | incident
 *  - genéricos de SLA/portfólio: warning|at_risk | critical|violated */
export function healthTone(status: string | null | undefined): Tone {
  switch (status?.toLowerCase()) {
    case "healthy":
    case "ok":
      return "green";
    case "warning":
    case "attention":
    case "at_risk":
    case "degraded":
      return "amber";
    case "critical":
    case "incident":
    case "violated":
    case "unhealthy":
      return "red";
    default:
      return "grey";
  }
}

/** Estado de SLA (`portfolio_catalog._sla_state`) → tom. */
export function slaTone(state: SlaState | null | undefined): Tone {
  switch (state?.toLowerCase()) {
    case "ok":
      return "green";
    case "breached":
      return "red";
    case "recovering":
      return "amber";
    default:
      return "grey"; // unknown
  }
}

/** Criticidade de catálogo → tom. */
export function criticalityTone(crit: string | null | undefined): Tone {
  switch (crit?.toLowerCase()) {
    case "high":
      return "red";
    case "medium":
      return "amber";
    case "low":
      return "cyan";
    default:
      return "grey";
  }
}

/** `Automation.operational_state` (backend, automation_snapshot.py
 *  `_resolve_operational_state`) → tom. Usado como fonte da lâmpada de
 *  status no card de automação — antes calculada localmente no front a
 *  partir só de `enabled`, ignorando execução em andamento/falha recente
 *  que o backend já resolve. */
export function operationalTone(state: string | null | undefined): Tone {
  switch (state?.toLowerCase()) {
    case "healthy":
      return "green";
    case "in_progress":
      return "cyan";
    case "attention":
      return "amber";
    case "paused":
    case "idle":
    default:
      return "grey";
  }
}

const OPERATIONAL_STATE_LABEL: Record<string, string> = {
  healthy: "saudável",
  in_progress: "em execução",
  attention: "atenção",
  paused: "pausada",
  idle: "ociosa",
};

export function operationalStateLabel(state: string | null | undefined): string {
  if (!state) return "—";
  return OPERATIONAL_STATE_LABEL[state.toLowerCase()] ?? state;
}

const HEALTH_LABEL: Record<string, string> = {
  healthy: "saudável",
  ok: "saudável",
  warning: "atenção",
  attention: "atenção",
  degraded: "degradado",
  critical: "incidente",
  incident: "incidente",
  unhealthy: "incidente",
};

export function healthLabel(status: string | null | undefined): string {
  if (!status) return "—";
  return HEALTH_LABEL[status.toLowerCase()] ?? status;
}
