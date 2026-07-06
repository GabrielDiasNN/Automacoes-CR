import { useMemo } from "react";
import { Search, X } from "lucide-react";
import type { BeneficiamentoFilterOptions } from "../../api/orchestrator";
import { Button } from "../ui";
import styles from "./FilterBar.module.css";

export interface BeneficiamentoFiltersState {
  dtInicio: string;
  dtFim: string;
  maquina: string;
  fase: string;
  turno: string;
  alternativo: string;
  q: string;
}

export const DEFAULT_BENEFICIAMENTO_FILTERS: BeneficiamentoFiltersState = {
  dtInicio: "",
  dtFim: "",
  maquina: "",
  fase: "",
  turno: "",
  alternativo: "",
  q: "",
};

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function presetRange(days: number): Pick<BeneficiamentoFiltersState, "dtInicio" | "dtFim"> {
  const fim = new Date();
  const inicio = new Date();
  inicio.setDate(inicio.getDate() - (days - 1));
  return { dtInicio: isoDate(inicio), dtFim: isoDate(fim) };
}

const PRESETS = [
  { label: "7d", days: 7 },
  { label: "30d", days: 30 },
  { label: "90d", days: 90 },
];

interface FilterBarProps {
  filters: BeneficiamentoFiltersState;
  options: BeneficiamentoFilterOptions | undefined;
  onChange: (patch: Partial<BeneficiamentoFiltersState>) => void;
  onReset: () => void;
}

function isActive(filters: BeneficiamentoFiltersState): boolean {
  return Object.values(filters).some((v) => v !== "");
}

/** Barra de filtros dinâmicos do Beneficiamento — datas, dimensões e busca livre. */
export function FilterBar({ filters, options, onChange, onReset }: FilterBarProps) {
  const active = useMemo(() => isActive(filters), [filters]);

  return (
    <div className={styles.bar}>
      <div className={styles.group}>
        {PRESETS.map((p) => (
          <Button key={p.label} size="sm" variant="subtle" onClick={() => onChange(presetRange(p.days))}>
            {p.label}
          </Button>
        ))}
        <input
          type="date"
          className={styles.date}
          value={filters.dtInicio}
          onChange={(e) => onChange({ dtInicio: e.target.value })}
          aria-label="Data inicial"
        />
        <span className={styles.sep}>até</span>
        <input
          type="date"
          className={styles.date}
          value={filters.dtFim}
          onChange={(e) => onChange({ dtFim: e.target.value })}
          aria-label="Data final"
        />
      </div>

      <div className={styles.group}>
        <select
          className={styles.select}
          value={filters.maquina}
          onChange={(e) => onChange({ maquina: e.target.value })}
          aria-label="Máquina"
        >
          <option value="">Todas as máquinas</option>
          {(options?.maquinas ?? []).map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
        <select
          className={styles.select}
          value={filters.fase}
          onChange={(e) => onChange({ fase: e.target.value })}
          aria-label="Fase"
        >
          <option value="">Todas as fases</option>
          {(options?.fases ?? []).map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
        <select
          className={styles.select}
          value={filters.turno}
          onChange={(e) => onChange({ turno: e.target.value })}
          aria-label="Turno"
        >
          <option value="">Todos os turnos</option>
          {(options?.turnos ?? []).map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
        <select
          className={styles.select}
          value={filters.alternativo}
          onChange={(e) => onChange({ alternativo: e.target.value })}
          aria-label="Produto"
        >
          <option value="">Todos os produtos</option>
          {(options?.alternativos ?? []).map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.searchGroup}>
        <Search size={13} className={styles.searchIcon} aria-hidden="true" />
        <input
          type="search"
          className={styles.search}
          placeholder="Buscar OB, produto, artigo, cor…"
          value={filters.q}
          onChange={(e) => onChange({ q: e.target.value })}
          aria-label="Busca livre"
        />
      </div>

      {active && (
        <Button size="sm" variant="ghost" icon={<X size={13} />} onClick={onReset}>
          Limpar
        </Button>
      )}
    </div>
  );
}
