import { formatNumber } from "../../lib/format";

const ISO_DATE_RE = /^(\d{4})-(\d{2})-(\d{2})T/;

const KPI_LABELS: Record<string, string> = {
  count: "Total de registros",
  fases: "Fases afetadas",
  lidos: "Registros lidos",
  novos: "Novos registros",
  alterados: "Alterados",
};

const OP_LABELS: Record<string, string> = {
  sum: "Total",
  max: "Máx.",
  min: "Mín.",
  avg: "Média",
  count: "Qtd.",
};

const COLUMN_LABELS: Record<string, string> = {
  NUMERO_OB: "Nº OB",
  PLACA_KANBAN: "Kanban",
  ALTERNATIVO: "Alternativo",
  CD_ARTIGO: "Artigo",
  CD_COR: "Cor",
  REDUZ_ACABADO: "Reduzido",
  DS_ITEM: "Produto",
  LARGURA: "Largura",
  GRAMATURA: "Gramatura",
  FASE_ATUAL: "Fase Atual",
  CODIGO_FASE: "Cód. Fase",
  STATUS_FASE_ATUAL: "Status",
  DIAS_PARADO: "Dias Parado",
  CODIGO_FLUXO: "Fluxo",
  QT_PECAS: "Peças",
  QT_KILOS_REAL: "KG Real",
  DT_ENTREGA: "Entrega",
  NOME_CLIENTE: "Cliente",
  KG_OB: "KG OB",
  METROS_OB: "Metros OB",
  DATA_EXPEDICAO_PROMETIDA: "Expedição Prometida",
  DIAS_ATE_EXPEDICAO: "Dias p/ Expedição",
  CLASSIFICACAO_RISCO: "Classificação de Risco",
};

export function formatCellValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return formatNumber(value);
  const str = String(value);
  const m = ISO_DATE_RE.exec(str);
  if (m) return `${m[3]}/${m[2]}/${m[1]}`;
  return str;
}

export function formatKpiLabel(key: string): string {
  if (KPI_LABELS[key]) return KPI_LABELS[key];
  const [op, col] = key.split(":");
  if (op && col) {
    const opLabel = OP_LABELS[op.toLowerCase()] ?? op.toUpperCase();
    const colLabel = COLUMN_LABELS[col] ?? col.replace(/_/g, " ");
    return `${opLabel} · ${colLabel}`;
  }
  return key.replace(/_/g, " ");
}

export function formatColumnHeader(col: string): string {
  return COLUMN_LABELS[col] ?? col.replace(/_/g, " ");
}

function sanitizeSpreadsheetCell(val: unknown): string {
  if (val === null || val === undefined) return "";
  const s = String(val);
  // Neutraliza Formula Injection (CSV/DDE) em textos iniciados por =, +, -, @, tab ou CR.
  if (typeof val !== "number" && /^[=+\-@\t\r]/.test(s)) {
    return `'${s}`;
  }
  return s;
}

export function exportRowsAsCsv(filename: string, columns: string[], rows: Record<string, unknown>[]) {
  const escape = (val: unknown) => {
    const s = sanitizeSpreadsheetCell(val);
    return /[;"\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const header = columns.map(escape).join(";");
  const lines = rows.map((row) => columns.map((c) => escape(row[c])).join(";"));
  const csv = `\uFEFF${[header, ...lines].join("\r\n")}`;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${filename}.csv`;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    a.remove();
  }, 0);
}

export function exportRowsAsExcel(filename: string, columns: string[], rows: Record<string, unknown>[]) {
  const escHtml = (val: unknown) =>
    sanitizeSpreadsheetCell(val)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  const ths = columns.map((c) => `<th>${escHtml(formatColumnHeader(c))}</th>`).join("");
  const trs = rows
    .map((r) => `<tr>${columns.map((c) => `<td>${escHtml(r[c])}</td>`).join("")}</tr>`)
    .join("");
  const html = `\uFEFF<html><head><meta charset="utf-8" /></head><body><table border="1"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table></body></html>`;
  const blob = new Blob([html], { type: "application/vnd.ms-excel;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${filename}.xls`;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    a.remove();
  }, 0);
}
