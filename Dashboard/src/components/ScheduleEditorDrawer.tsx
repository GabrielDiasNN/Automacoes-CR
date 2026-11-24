import { useEffect, useRef, useState } from "react";
import { CalendarClock, CheckCircle2, Eye, Save } from "lucide-react";
import { orchestratorApi, type Automation, type SchedulePreviewResponse } from "../api/orchestrator";
import { Button, Card, Drawer, Input, Select, StatusTag, useToast } from "./ui";
import { errMessage } from "../lib/errors";
import page from "../pages/page.module.css";

type ScheduleKind = "manual" | "daily" | "weekly" | "interval" | "cron" | "preserved";

const WEEKDAYS = [
  { id: 1, label: "Seg" },
  { id: 2, label: "Ter" },
  { id: 3, label: "Qua" },
  { id: 4, label: "Qui" },
  { id: 5, label: "Sex" },
  { id: 6, label: "Sáb" },
  { id: 0, label: "Dom" },
];
const ALL_WEEKDAYS = [1, 2, 3, 4, 5, 6, 0];
const HH_MM_24H_RE = /^([01]\d|2[0-3]):([0-5]\d)$/;

interface ParsedForm {
  kind: ScheduleKind;
  times: string;
  intervalMinutes: number;
  startTime: string;
  endTime: string;
  anchorTime: string;
  days: number[];
  cronExpressions: string;
  cronWasArray: boolean;
  preservedKind: string | null;
  preservedRaw: string | null;
}

function formatTimeEntry(entry: unknown): string | null {
  if (typeof entry === "string") return entry.trim() || null;
  if (entry && typeof entry === "object") {
    const rec = entry as Record<string, unknown>;
    const h = Number(rec.h);
    const m = Number(rec.m);
    if (Number.isInteger(h) && Number.isInteger(m) && h >= 0 && h <= 23 && m >= 0 && m <= 59) {
      return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
    }
  }
  return null;
}

function findInvalidTimes(raw: string): string[] {
  const invalid: string[] = [];
  for (const part of raw.split(",")) {
    const clean = part.trim();
    if (!clean) continue;
    const match = /^(\d{1,2}):(\d{2})$/.exec(clean);
    if (!match) {
      invalid.push(clean);
      continue;
    }
    const h = Number(match[1]);
    const m = Number(match[2]);
    if (h < 0 || h > 23 || m < 0 || m > 59) {
      invalid.push(clean);
    }
  }
  return invalid;
}

function parseTimesToBackend(raw: string): { h: number; m: number }[] {
  const result: { h: number; m: number }[] = [];
  for (const part of raw.split(",")) {
    const clean = part.trim();
    const match = /^(\d{1,2}):(\d{2})$/.exec(clean);
    if (!match) continue;
    const h = Number(match[1]);
    const m = Number(match[2]);
    if (h >= 0 && h <= 23 && m >= 0 && m <= 59) {
      result.push({ h, m });
    }
  }
  return result;
}

function parseCronList(raw: string): string[] {
  return raw
    .split(/[;\n]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function parseInitialSchedule(raw: string | null): ParsedForm {
  const fallback: ParsedForm = {
    kind: "manual",
    times: "07:00, 14:00",
    intervalMinutes: 60,
    startTime: "05:00",
    endTime: "19:00",
    anchorTime: "",
    days: [1, 2, 3, 4, 5],
    cronExpressions: "0 7-17 * * mon-fri",
    cronWasArray: false,
    preservedKind: null,
    preservedRaw: null,
  };
  if (!raw) return fallback;
  try {
    const obj = JSON.parse(raw) as Record<string, unknown>;
    const st = String(obj.schedule_type ?? "manual").toLowerCase();
    const isEditable = st === "manual" || st === "daily" || st === "weekly" || st === "interval" || st === "cron";
    const kind: ScheduleKind = isEditable ? st : "preserved";
    const timesArr = Array.isArray(obj.times)
      ? obj.times.map(formatTimeEntry).filter((v): v is string => v !== null)
      : [];
    const hasExplicitDays = Array.isArray(obj.days_of_week) || Array.isArray(obj.daysOfWeek);
    const rawDays = Array.isArray(obj.days_of_week)
      ? obj.days_of_week
      : Array.isArray(obj.daysOfWeek)
        ? obj.daysOfWeek
        : [];
    const daysArr = rawDays.map(Number).filter((n) => Number.isInteger(n) && n >= 0 && n <= 6);
    const cronRaw = obj.cron_expression;
    const cronWasArray = Array.isArray(cronRaw);
    const cronList = cronWasArray
      ? cronRaw.map((c) => String(c).trim()).filter(Boolean)
      : typeof cronRaw === "string" && cronRaw.trim()
        ? [cronRaw.trim()]
        : [];
    const intervalStart =
      typeof obj.start_time === "string" ? obj.start_time.trim() : st === "interval" ? "" : fallback.startTime;
    const intervalEnd =
      typeof obj.end_time === "string" ? obj.end_time.trim() : st === "interval" ? "" : fallback.endTime;
    const intervalDays = hasExplicitDays ? daysArr : st === "interval" ? ALL_WEEKDAYS : fallback.days;

    return {
      kind,
      times: timesArr.length > 0 ? timesArr.join(", ") : fallback.times,
      intervalMinutes: Number(obj.interval_minutes ?? obj.every_minutes ?? 60) || 60,
      startTime: intervalStart,
      endTime: intervalEnd,
      anchorTime: typeof obj.anchor_time === "string" ? obj.anchor_time.trim() : "",
      days: intervalDays,
      cronExpressions: cronList.length > 0 ? cronList.join("; ") : fallback.cronExpressions,
      cronWasArray,
      preservedKind: kind === "preserved" ? st : null,
      preservedRaw: kind === "preserved" ? raw : null,
    };
  } catch {
    return fallback;
  }
}

function buildScheduleJson(form: ParsedForm): string | null {
  if (form.kind === "preserved") return form.preservedRaw;
  if (form.kind === "manual") return null;
  if (form.kind === "cron") {
    const exprs = parseCronList(form.cronExpressions);
    const cronExpression =
      exprs.length <= 1 && !form.cronWasArray ? (exprs[0] ?? "") : exprs;
    return JSON.stringify({
      schedule_version: 2,
      schedule_type: "cron",
      cron_expression: cronExpression,
      timezone: "America/Sao_Paulo",
    });
  }
  const times = parseTimesToBackend(form.times);
  if (form.kind === "daily") {
    return JSON.stringify({
      schedule_version: 2,
      schedule_type: "daily",
      times,
      timezone: "America/Sao_Paulo",
    });
  }
  if (form.kind === "weekly") {
    return JSON.stringify({
      schedule_version: 2,
      schedule_type: "weekly",
      days_of_week: form.days,
      times,
      timezone: "America/Sao_Paulo",
    });
  }
  return JSON.stringify({
    schedule_version: 2,
    schedule_type: "interval",
    interval_minutes: Math.min(1440, Math.max(1, Math.floor(form.intervalMinutes))),
    days_of_week: form.days.length === ALL_WEEKDAYS.length ? undefined : form.days,
    start_time: form.startTime.trim() || undefined,
    end_time: form.endTime.trim() || undefined,
    anchor_time: form.anchorTime.trim() || undefined,
    timezone: "America/Sao_Paulo",
  });
}

export function ScheduleEditorDrawer({
  automation,
  onClose,
  onSaved,
}: {
  automation: Automation | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState<ParsedForm>(() => parseInitialSchedule(null));
  const [preview, setPreview] = useState<SchedulePreviewResponse | null>(null);
  const [busy, setBusy] = useState<"preview" | "save" | null>(null);
  const requestSeqRef = useRef(0);

  useEffect(() => {
    const seq = ++requestSeqRef.current;
    setBusy(null);
    setPreview(null);
    if (!automation) return () => {
      if (requestSeqRef.current === seq) requestSeqRef.current += 1;
    };
    setForm(parseInitialSchedule(automation.schedule));
    return () => {
      if (requestSeqRef.current === seq) requestSeqRef.current += 1;
    };
  }, [automation]);

  const toggleDay = (day: number) => {
    setForm((prev) => ({
      ...prev,
      days: prev.days.includes(day) ? prev.days.filter((d) => d !== day) : [...prev.days, day],
    }));
  };

  const validateForm = (): string | null => {
    if (form.kind === "daily" || form.kind === "weekly") {
      const invalid = findInvalidTimes(form.times);
      if (invalid.length > 0) {
        return `Horário(s) inválido(s): ${invalid.join(", ")}. Use o formato HH:MM.`;
      }
      if (parseTimesToBackend(form.times).length === 0) {
        return "Informe ao menos um horário válido no formato HH:MM.";
      }
    }
    if ((form.kind === "weekly" || form.kind === "interval") && form.days.length === 0) {
      return "Selecione ao menos um dia da semana.";
    }
    if (form.kind === "interval") {
      if (!Number.isInteger(form.intervalMinutes) || form.intervalMinutes < 1 || form.intervalMinutes > 1440) {
        return "Intervalo deve ser um número inteiro entre 1 e 1440 minutos.";
      }
      const st = form.startTime.trim();
      const et = form.endTime.trim();
      if (st && !HH_MM_24H_RE.test(st)) {
        return "Horário inicial inválido. Use HH:MM (00:00 a 23:59).";
      }
      if (et && !HH_MM_24H_RE.test(et)) {
        return "Horário final inválido. Use HH:MM (00:00 a 23:59).";
      }
      if (st && et && st > et) {
        return "Horário inicial da janela não pode ser maior que o horário final.";
      }
    }
    if (form.kind === "cron") {
      const exprs = parseCronList(form.cronExpressions);
      if (exprs.length === 0) {
        return "Informe ao menos uma expressão cron válida.";
      }
      if (exprs.some((expr) => expr.split(/\s+/).length !== 5)) {
        return "Cada expressão cron deve conter exatamente 5 campos (ex.: 0 7-17 * * mon-fri).";
      }
    }
    return null;
  };

  const runPreview = async () => {
    const validationErr = validateForm();
    if (validationErr) {
      toast(validationErr, "red");
      return;
    }
    const seq = requestSeqRef.current;
    setBusy("preview");
    try {
      const schedule = buildScheduleJson(form);
      const res = await orchestratorApi.previewSchedule(schedule, 5);
      if (seq !== requestSeqRef.current) return;
      setPreview(res);
    } catch (e) {
      if (seq !== requestSeqRef.current) return;
      toast(errMessage(e), "red");
    } finally {
      if (seq === requestSeqRef.current) setBusy(null);
    }
  };

  const save = async () => {
    if (!automation || form.kind === "preserved") return;
    const validationErr = validateForm();
    if (validationErr) {
      toast(validationErr, "red");
      return;
    }
    const seq = requestSeqRef.current;
    setBusy("save");
    try {
      await orchestratorApi.updateAutomation(automation.id, {
        schedule: buildScheduleJson(form),
      });
      if (seq !== requestSeqRef.current) return;
      toast(`Agenda de "${automation.name}" atualizada.`, "green");
      onSaved();
      onClose();
    } catch (e) {
      if (seq !== requestSeqRef.current) return;
      toast(errMessage(e), "red");
    } finally {
      if (seq === requestSeqRef.current) setBusy(null);
    }
  };

  const handleClose = () => {
    if (busy === "save") return;
    onClose();
  };

  return (
    <Drawer
      open={!!automation}
      onClose={handleClose}
      eyebrow="Configuração de Agenda & SLA"
      title={automation?.name}
      width={560}
    >
      {automation && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
          <Card label="Recorrência e Horários">
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <label htmlFor="sched-kind" style={{ fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
                  Tipo de agendamento
                </label>
                <Select
                  id="sched-kind"
                  value={form.kind}
                  onChange={(e) => setForm((p) => ({ ...p, kind: e.target.value as ScheduleKind }))}
                  aria-label="Tipo de agendamento"
                >
                  {form.preservedRaw !== null && (
                    <option value="preserved">
                      Preservado ({form.preservedKind ?? "avançado"})
                    </option>
                  )}
                  <option value="manual">Manual (somente sob demanda)</option>
                  <option value="daily">Diário (horários fixos todos os dias)</option>
                  <option value="weekly">Semanal (dias da semana + horários)</option>
                  <option value="interval">Intervalo contínuo (a cada N minutos)</option>
                  <option value="cron">Cron (expressão crontab)</option>
                </Select>
              </div>

              {form.kind === "preserved" && (
                <p style={{ margin: 0, fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
                  Agenda atual ({automation.schedule_summary ?? form.preservedKind ?? "avançada"}) está preservada
                  inalterada. Para substituí-la, escolha outro tipo de agendamento acima.
                </p>
              )}

              {form.kind === "cron" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label htmlFor="sched-cron" style={{ fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
                    Expressões cron (5 campos, separadas por ponto e vírgula; dia da semana: 0=Seg..6=Dom ou mon-sun)
                  </label>
                  <Input
                    id="sched-cron"
                    value={form.cronExpressions}
                    onChange={(e) => setForm((p) => ({ ...p, cronExpressions: e.target.value }))}
                    placeholder="0 7-17 * * mon-fri"
                    aria-label="Expressões cron"
                  />
                </div>
              )}

              {(form.kind === "daily" || form.kind === "weekly") && (
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label htmlFor="sched-times" style={{ fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
                    Horários (HH:MM separados por vírgula)
                  </label>
                  <Input
                    id="sched-times"
                    value={form.times}
                    onChange={(e) => setForm((p) => ({ ...p, times: e.target.value }))}
                    placeholder="07:00, 11:00, 14:00, 17:00"
                    aria-label="Horários de execução"
                  />
                </div>
              )}

              {form.kind === "interval" && (
                <div className={page.split}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <label htmlFor="sched-interval" style={{ fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
                      A cada (minutos)
                    </label>
                    <Input
                      id="sched-interval"
                      type="number"
                      min={1}
                      max={1440}
                      value={String(form.intervalMinutes)}
                      onChange={(e) => setForm((p) => ({ ...p, intervalMinutes: Number(e.target.value) || 0 }))}
                      aria-label="Intervalo em minutos"
                    />
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--sp-2)" }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <label htmlFor="sched-start" style={{ fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
                        Início (opcional)
                      </label>
                      <Input
                        id="sched-start"
                        value={form.startTime}
                        onChange={(e) => setForm((p) => ({ ...p, startTime: e.target.value }))}
                        placeholder="05:00"
                        aria-label="Horário inicial da janela"
                      />
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <label htmlFor="sched-end" style={{ fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
                        Fim (opcional)
                      </label>
                      <Input
                        id="sched-end"
                        value={form.endTime}
                        onChange={(e) => setForm((p) => ({ ...p, endTime: e.target.value }))}
                        placeholder="19:00"
                        aria-label="Horário final da janela"
                      />
                    </div>
                  </div>
                </div>
              )}

              {(form.kind === "weekly" || form.kind === "interval") && (
                <div>
                  <div className={page.sectionLabel}>Dias da semana</div>
                  <div role="group" aria-label="Dias da semana" style={{ display: "flex", gap: "var(--sp-1)", flexWrap: "wrap" }}>
                    {WEEKDAYS.map((d) => {
                      const active = form.days.includes(d.id);
                      return (
                        <Button
                          key={d.id}
                          size="sm"
                          variant={active ? "primary" : "ghost"}
                          aria-pressed={active}
                          onClick={() => toggleDay(d.id)}
                        >
                          {d.label}
                        </Button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </Card>

          <Card label="Parâmetros Operacionais (Manifesto)">
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2)" }}>
              <div className={page.tiles}>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label htmlFor="sched-sla" style={{ fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
                    SLA (min)
                  </label>
                  <Input
                    id="sched-sla"
                    value={automation.sla_minutes != null ? String(automation.sla_minutes) : "—"}
                    readOnly
                    disabled
                    aria-label="SLA em minutos"
                  />
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label htmlFor="sched-timeout" style={{ fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
                    Timeout (min)
                  </label>
                  <Input
                    id="sched-timeout"
                    value={String(automation.max_runtime_minutes)}
                    readOnly
                    disabled
                    aria-label="Tempo máximo de execução"
                  />
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label htmlFor="sched-retries" style={{ fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
                    Tentativas (retries)
                  </label>
                  <Input
                    id="sched-retries"
                    value={String(automation.max_retries)}
                    readOnly
                    disabled
                    aria-label="Máximo de retentativas"
                  />
                </div>
              </div>
              <p style={{ margin: 0, fontSize: "var(--fs-label)", color: "var(--text-lo)" }}>
                Parâmetros governados por automation.manifest.json (somente leitura neste editor).
              </p>
            </div>
          </Card>

          {preview && (
            <Card label="Simulação das Próximas Execuções" alert={!preview.valid}>
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2)" }}>
                <StatusTag tone={preview.valid ? "green" : "red"} dot>
                  {preview.valid ? preview.schedule_summary ?? "Agenda válida" : "Agenda inválida"}
                </StatusTag>
                {preview.errors.length > 0 && (
                  <ul style={{ margin: 0, paddingLeft: "var(--sp-4)", color: "var(--red)", fontSize: "var(--fs-small)" }}>
                    {preview.errors.map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                )}
                {preview.next_runs_preview.length > 0 && (
                  <ul style={{ margin: 0, paddingLeft: "var(--sp-4)", fontFamily: "var(--font-mono)", fontSize: "var(--fs-label)", color: "var(--text-mid)" }}>
                    {preview.next_runs_preview.map((runAt) => (
                      <li key={runAt}>
                        <CalendarClock size={11} style={{ marginRight: 6, verticalAlign: "-1px" }} />
                        {runAt}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </Card>
          )}

          <div className={page.toolbar}>
            <Button
              size="sm"
              variant="ghost"
              icon={<Eye size={13} />}
              disabled={busy !== null}
              onClick={() => void runPreview()}
            >
              {busy === "preview" ? "Simulando…" : "Simular próximas execuções"}
            </Button>
            <span className={page.filler} />
            <Button size="sm" variant="subtle" onClick={handleClose} disabled={busy === "save"}>
              Cancelar
            </Button>
            <Button
              size="sm"
              variant="primary"
              icon={busy === "save" ? <CheckCircle2 size={13} /> : <Save size={13} />}
              disabled={busy !== null || form.kind === "preserved"}
              onClick={() => void save()}
            >
              {busy === "save" ? "Salvando…" : "Salvar alterações"}
            </Button>
          </div>
        </div>
      )}
    </Drawer>
  );
}
