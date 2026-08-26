/** Mapeamento central status/severidade → tom de cor + rótulo.
 *  Fonte única de verdade (antes espalhado em cada página). */

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

/** Estado de execução → tom. */
export function executionTone(status: string): Tone {
  switch (status?.toUpperCase()) {
    case "SUCCESS":
      return "green";
    case "ERROR":
    case "TIMEOUT":
      return "red";
    case "RUNNING":
    case "CLAIMED":
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

/** Saúde de sistema / baseline → tom. */
export function healthTone(status: string | null | undefined): Tone {
  switch (status?.toLowerCase()) {
    case "healthy":
    case "ok":
      return "green";
    case "warning":
    case "attention":
    case "at_risk":
      return "amber";
    case "critical":
    case "incident":
    case "violated":
      return "red";
    default:
      return "grey";
  }
}

/** Estado de SLA → tom. */
export function slaTone(state: string | null | undefined): Tone {
  switch (state?.toLowerCase()) {
    case "ok":
      return "green";
    case "at_risk":
      return "amber";
    case "violated":
      return "red";
    default:
      return "grey";
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

const HEALTH_LABEL: Record<string, string> = {
  healthy: "saudável",
  warning: "atenção",
  attention: "atenção",
  critical: "incidente",
  incident: "incidente",
};

export function healthLabel(status: string | null | undefined): string {
  if (!status) return "—";
  return HEALTH_LABEL[status.toLowerCase()] ?? status;
}
