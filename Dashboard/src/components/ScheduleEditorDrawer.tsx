import { useEffect, useState } from "react";
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

interface ParsedForm {
  kind: ScheduleKind;
  times: string;
  intervalMinutes: number;
  startTime: string;
  endTime: string;
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
    days: [1, 2, 3, 4, 5],
    cronExpressions: "0 7-17 * * 1-5",
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
    return {
      kind,
      times: timesArr.length > 0 ? timesArr.join(", ") : fallback.times,
      intervalMinutes: Number(obj.interval_minutes ?? obj.every_minutes ?? 60) || 60,
      startTime: typeof obj.start_time === "string" ? obj.start_time : fallback.startTime,
      endTime: typeof obj.end_time === "string" ? obj.end_time : fallback.endTime,
      days: daysArr.length > 0 ? daysArr : fallback.days,
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
    interval_minutes: Math.max(1, form.intervalMinutes),
    days_of_week: form.days,
    start_time: form.startTime || undefined,
    end_time: form.endTime || undefined,
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
  const [slaMinutes, setSlaMinutes] = useState("");
  const [maxRuntime, setMaxRuntime] = useState("30");
  const [maxRetries, setMaxRetries] = useState("0");
  const [preview, setPreview] = useState<SchedulePreviewResponse | null>(null);
  const [busy, setBusy] = useState<"preview" | "save" | null>(null);

  useEffect(() => {
    if (!automation) return;
    setForm(parseInitialSchedule(automation.schedule));
    setSlaMinutes(automation.sla_minutes != null ? String(automation.sla_minutes) : "");
    setMaxRuntime(String(automation.max_runtime_minutes));
    setMaxRetries(String(automation.max_retries));
    setPreview(null);
  }, [automation]);

  const toggleDay = (day: number) => {
    setForm((prev) => ({
      ...prev,
      days: prev.days.includes(day) ? prev.days.filter((d) => d !== day) : [...prev.days, day],
    }));
  };

  const runPreview = async () => {
    setBusy("preview");
    try {
      const schedule = buildScheduleJson(form);
      const res = await orchestratorApi.previewSchedule(schedule, 5);
      setPreview(res);
    } catch (e) {
      toast(errMessage(e), "red");
    } finally {
      setBusy(null);
    }
  };

  const save = async () => {
    if (!automation) return;
    if ((form.kind === "daily" || form.kind === "weekly") && parseTimesToBackend(form.times).length === 0) {
      toast("Informe ao menos um horário válido no formato HH:MM.", "red");
      return;
    }
    if (form.kind === "weekly" && form.days.length === 0) {
      toast("Selecione ao menos um dia da semana.", "red");
      return;
    }
    if (form.kind === "cron" && parseCronList(form.cronExpressions).length === 0) {
      toast("Informe ao menos uma expressão cron válida.", "red");
      return;
    }
    setBusy("save");
    try {
      const slaNum = slaMinutes.trim() ? Number(slaMinutes) : null;
      const payload: Parameters<typeof orchestratorApi.updateAutomation>[1] = {
        sla_minutes: slaNum && Number.isFinite(slaNum) ? slaNum : null,
        max_runtime_minutes: Math.max(1, Number(maxRuntime) || automation.max_runtime_minutes),
        max_retries: Math.max(0, Number(maxRetries) || 0),
      };
      if (form.kind !== "preserved") {
        payload.schedule = buildScheduleJson(form);
      }
      await orchestratorApi.updateAutomation(automation.id, payload);
      toast(`Agenda de "${automation.name}" atualizada.`, "green");
      onSaved();
      onClose();
    } catch (e) {
      toast(errMessage(e), "red");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Drawer
      open={!!automation}
      onClose={onClose}
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
                  {form.kind === "preserved" && (
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
                  Agenda atual ({automation.schedule_summary ?? form.preservedKind ?? "avançada"}) será preservada
                  inalterada ao salvar parâmetros operacionais.
                </p>
              )}

              {form.kind === "cron" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label htmlFor="sched-cron" style={{ fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
                    Expressões cron (5 campos, separadas por ponto e vírgula)
                  </label>
                  <Input
                    id="sched-cron"
                    value={form.cronExpressions}
                    onChange={(e) => setForm((p) => ({ ...p, cronExpressions: e.target.value }))}
                    placeholder="0 7-17 * * 1-5"
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
                      onChange={(e) => setForm((p) => ({ ...p, intervalMinutes: Number(e.target.value) || 1 }))}
                      aria-label="Intervalo em minutos"
                    />
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--sp-2)" }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <label htmlFor="sched-start" style={{ fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
                        Início
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
                        Fim
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
                  <div style={{ display: "flex", gap: "var(--sp-1)", flexWrap: "wrap" }}>
                    {WEEKDAYS.map((d) => {
                      const active = form.days.includes(d.id);
                      return (
                        <Button
                          key={d.id}
                          size="sm"
                          variant={active ? "primary" : "ghost"}
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

          <Card label="Parâmetros Operacionais">
            <div className={page.tiles}>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <label htmlFor="sched-sla" style={{ fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
                  SLA (min)
                </label>
                <Input
                  id="sched-sla"
                  type="number"
                  min={1}
                  value={slaMinutes}
                  onChange={(e) => setSlaMinutes(e.target.value)}
                  placeholder="ex: 60"
                  aria-label="SLA em minutos"
                />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <label htmlFor="sched-timeout" style={{ fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
                  Timeout (min)
                </label>
                <Input
                  id="sched-timeout"
                  type="number"
                  min={1}
                  max={480}
                  value={maxRuntime}
                  onChange={(e) => setMaxRuntime(e.target.value)}
                  aria-label="Tempo máximo de execução"
                />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <label htmlFor="sched-retries" style={{ fontSize: "var(--fs-small)", color: "var(--text-mid)" }}>
                  Tentativas (retries)
                </label>
                <Input
                  id="sched-retries"
                  type="number"
                  min={0}
                  max={10}
                  value={maxRetries}
                  onChange={(e) => setMaxRetries(e.target.value)}
                  aria-label="Máximo de retentativas"
                />
              </div>
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
            <Button size="sm" variant="subtle" onClick={onClose} disabled={busy === "save"}>
              Cancelar
            </Button>
            <Button
              size="sm"
              variant="primary"
              icon={busy === "save" ? <CheckCircle2 size={13} /> : <Save size={13} />}
              disabled={busy !== null}
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
