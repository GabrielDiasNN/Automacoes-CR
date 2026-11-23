import { useMemo } from "react";
import { CalendarClock } from "lucide-react";
import type { Automation } from "../api/orchestrator";
import { Card, StatusTag } from "./ui";
import styles from "./ScheduleTimeline24h.module.css";

export interface TimelineSlot {
  automation: Automation;
  hour: number;
  minute: number;
  timeLabel: string;
}

function parseTimeEntry(entry: unknown): { hour: number; minute: number } | null {
  if (typeof entry === "string") {
    const match = /^(\d{1,2}):(\d{2})$/.exec(entry.trim());
    if (!match) return null;
    const hour = Number(match[1]);
    const minute = Number(match[2]);
    if (hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59) {
      return { hour, minute };
    }
    return null;
  }
  if (entry && typeof entry === "object") {
    const rec = entry as Record<string, unknown>;
    if (typeof rec.h !== "number" || typeof rec.m !== "number") return null;
    const { h: hour, m: minute } = rec;
    if (Number.isInteger(hour) && Number.isInteger(minute) && hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59) {
      return { hour, minute };
    }
  }
  return null;
}

function expandCronField(field: string, min: number, max: number): number[] {
  const out = new Set<number>();
  for (const rawPart of field.split(",")) {
    const part = rawPart.trim();
    if (!part) continue;
    const [rangePart, stepPart] = part.split("/");
    const step = stepPart ? Number(stepPart) : 1;
    if (!Number.isInteger(step) || step <= 0) continue;

    let start = min;
    let end = max;
    if (rangePart !== "*") {
      if (rangePart?.includes("-")) {
        const [a, b] = rangePart.split("-");
        const na = Number(a);
        const nb = Number(b);
        if (!Number.isInteger(na) || !Number.isInteger(nb)) continue;
        start = Math.max(min, na);
        end = Math.min(max, nb);
      } else {
        const n = Number(rangePart);
        if (!Number.isInteger(n)) continue;
        if (n < min || n > max) continue;
        start = n;
        end = stepPart ? max : n;
      }
    }
    for (let v = start; v <= end; v += step) {
      out.add(v);
    }
  }
  return [...out].sort((a, b) => a - b);
}

function extractCronTimes(expr: string): { hour: number; minute: number }[] {
  const parts = expr.trim().split(/\s+/);
  if (parts.length < 5) return [];
  const minutes = expandCronField(parts[0]!, 0, 59);
  const hours = expandCronField(parts[1]!, 0, 23);
  if (minutes.length === 0 || hours.length === 0) return [];
  // Alta frequência (ex.: "* * * * *" ou "*/5"): amostra até 4 pontos por hora para manter a régua legível.
  const sampledMinutes = minutes.length > 6 ? [minutes[0]!] : minutes;
  const result: { hour: number; minute: number }[] = [];
  for (const hour of hours) {
    for (const minute of sampledMinutes) {
      result.push({ hour, minute });
    }
  }
  return result;
}

function parseHhMmToMinutes(raw: unknown): number | null {
  if (typeof raw !== "string") return null;
  const match = /^(\d{1,2}):(\d{2})$/.exec(raw.trim());
  if (!match) return null;
  const h = Number(match[1]);
  const m = Number(match[2]);
  if (h >= 0 && h <= 23 && m >= 0 && m <= 59) return h * 60 + m;
  return null;
}

function extractIntervalTimes(parsed: Record<string, unknown>): { hour: number; minute: number }[] {
  const step = Number(parsed.interval_minutes ?? parsed.every_minutes);
  if (!Number.isFinite(step) || step < 1 || step > 1440) return [];
  const startMin = parseHhMmToMinutes(parsed.start_time) ?? 0;
  const endMin = parseHhMmToMinutes(parsed.end_time) ?? 23 * 60 + 59;
  const anchorMin = parseHhMmToMinutes(parsed.anchor_time) ?? startMin;
  if (startMin > endMin) return [];

  const effectiveStep = step < 15 ? 60 : Math.floor(step);
  let cur = anchorMin;
  while (cur < startMin) cur += effectiveStep;
  while (cur - effectiveStep >= startMin) cur -= effectiveStep;

  const result: { hour: number; minute: number }[] = [];
  for (; cur <= endMin; cur += effectiveStep) {
    result.push({ hour: Math.floor(cur / 60), minute: cur % 60 });
  }
  return result;
}

export function extractScheduledSlots(automations: Automation[]): TimelineSlot[] {
  const slots: TimelineSlot[] = [];
  for (const automation of automations) {
    if (!automation.enabled || !automation.schedule) continue;
    let parsed: unknown;
    try {
      parsed = JSON.parse(automation.schedule);
    } catch {
      continue;
    }
    if (!parsed || typeof parsed !== "object") continue;
    const obj = parsed as Record<string, unknown>;
    const st = String(obj.schedule_type ?? "").toLowerCase();

    let candidates: { hour: number; minute: number }[] = [];
    if (st === "cron") {
      const rawExprs = obj.cron_expression;
      const exprList = Array.isArray(rawExprs)
        ? rawExprs.map((e) => String(e))
        : typeof rawExprs === "string"
          ? [rawExprs]
          : [];
      for (const expr of exprList) {
        candidates.push(...extractCronTimes(expr));
      }
    } else if (st === "interval") {
      candidates = extractIntervalTimes(obj);
    } else if (Array.isArray(obj.times)) {
      candidates = obj.times
        .map(parseTimeEntry)
        .filter((t): t is { hour: number; minute: number } => t !== null);
    }

    const seen = new Set<string>();
    for (const time of candidates) {
      const timeLabel = `${String(time.hour).padStart(2, "0")}:${String(time.minute).padStart(2, "0")}`;
      if (seen.has(timeLabel)) continue;
      seen.add(timeLabel);
      slots.push({
        automation,
        hour: time.hour,
        minute: time.minute,
        timeLabel,
      });
    }
  }
  return slots;
}

export interface ScheduleTimeline24hProps {
  automations: Automation[];
  onSelectAutomation: (automation: Automation) => void;
}

export function ScheduleTimeline24h({ automations, onSelectAutomation }: ScheduleTimeline24hProps) {
  const { buckets, totalSlots, congestedHours } = useMemo(() => {
    const slots = extractScheduledSlots(automations);
    const byHour: TimelineSlot[][] = Array.from({ length: 24 }, () => []);
    for (const slot of slots) {
      byHour[slot.hour]!.push(slot);
    }
    for (const list of byHour) {
      list.sort((a, b) => a.minute - b.minute || a.automation.name.localeCompare(b.automation.name, "pt-BR"));
    }
    const congested = byHour
      .map((list, hour) => (list.length >= 2 ? hour : -1))
      .filter((hour) => hour >= 0);
    return {
      buckets: byHour,
      totalSlots: slots.length,
      congestedHours: congested,
    };
  }, [automations]);

  return (
    <Card>
      <section className={styles.wrap} aria-label="Timeline visual de agendas 24h">
        <div className={styles.header}>
          <div className={styles.titleGroup}>
            <CalendarClock size={16} aria-hidden="true" />
            <h2 className={styles.title}>Timeline de Agendas 24h</h2>
          </div>
          <div className={styles.summary}>
            <span className={styles.meta}>
              {totalSlots} {totalSlots === 1 ? "disparo ativo" : "disparos ativos"}
            </span>
            {congestedHours.length > 0 && (
              <StatusTag tone="amber" dot>
                {congestedHours.length === 1
                  ? "1 hora congestionada (≥ 2 disparos)"
                  : `${congestedHours.length} horas congestionadas (≥ 2 disparos)`}
              </StatusTag>
            )}
          </div>
        </div>

        {totalSlots === 0 ? (
          <p className={styles.empty}>Nenhum disparo com horário fixo ativo nas 24h.</p>
        ) : (
          <div className={styles.scrollArea}>
            <div className={styles.ruler} role="list" aria-label="Régua horária de 00h a 23h">
              {buckets.map((hourSlots, hour) => {
                const hourText = `${String(hour).padStart(2, "0")}h`;
                const isCongested = hourSlots.length >= 2;
                const colClass = [
                  styles.hourCol,
                  hourSlots.length > 0 ? styles.hourActive : "",
                  isCongested ? styles.hourCongested : "",
                ]
                  .filter(Boolean)
                  .join(" ");

                return (
                  <div
                    key={hour}
                    role="listitem"
                    className={colClass}
                    data-hour={hour}
                    data-congested={isCongested ? "true" : "false"}
                    aria-label={
                      isCongested
                        ? `${hourText} — congestionada (${hourSlots.length} disparos)`
                        : `${hourText} (${hourSlots.length} ${hourSlots.length === 1 ? "disparo" : "disparos"})`
                    }
                  >
                    <div className={styles.hourHeader}>
                      <span className={styles.hourLabel}>{hourText}</span>
                      {hourSlots.length > 0 && <span className={styles.hourCount}>{hourSlots.length}</span>}
                    </div>
                    <div className={styles.slots}>
                      {hourSlots.map((slot) => (
                        <button
                          key={`${slot.automation.id}-${slot.timeLabel}`}
                          type="button"
                          className={styles.slotBtn}
                          title={`${slot.timeLabel} — ${slot.automation.name}`}
                          aria-label={`Editar agenda de ${slot.automation.name} às ${slot.timeLabel}`}
                          onClick={() => onSelectAutomation(slot.automation)}
                        >
                          <span className={styles.slotTime}>{slot.timeLabel}</span>
                          <span className={styles.slotName}>{slot.automation.name}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </section>
    </Card>
  );
}
