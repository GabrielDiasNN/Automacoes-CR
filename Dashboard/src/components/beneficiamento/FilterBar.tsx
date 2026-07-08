import { useMemo } from "react";
import { Search, X } from "lucide-react";
import type { BeneficiamentoFilterOptions } from "../../api/orchestrator";
import { Button } from "../ui";
import { ProductAutocomplete } from "./ProductAutocomplete";
import styles from "./FilterBar.module.css";

export interface BeneficiamentoFiltersState {
  dtInicio: string;
  dtFim: string;
  maquina: string;
  fase: string;
  turno: string;
  alternativo: string;
  q: string;
  setor: string;
  grupoFase: string;
  tipoMaquina: string;
  reprocesso: string;
  status: string;
}

export const DEFAULT_BENEFICIAMENTO_FILTERS: BeneficiamentoFiltersState = {
  dtInicio: "",
  dtFim: "",
  maquina: "",
  fase: "",
  turno: "",
  alternativo: "",
  q: "",
  setor: "",
  grupoFase: "",
  tipoMaquina: "",
  reprocesso: "",
  status: "",
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
          value={filters.setor}
          onChange={(e) => onChange({ setor: e.target.value, grupoFase: "", fase: "" })}
          aria-label="Setor industrial"
        >
          <option value="">Todos os setores</option>
          {(options?.setores ?? []).map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
        <select
          className={styles.select}
          value={filters.grupoFase}
          onChange={(e) => onChange({ grupoFase: e.target.value, fase: "" })}
          aria-label="Grupo de fase"
        >
          <option value="">Todos os grupos de fase</option>
          {(options?.grupos_fase ?? []).map((v) => (
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
          value={filters.tipoMaquina}
          onChange={(e) => onChange({ tipoMaquina: e.target.value })}
          aria-label="Tipo de máquina"
        >
          <option value="">Todos os tipos de máquina</option>
          {(options?.tipos_maquina ?? []).map((v) => (
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
        <ProductAutocomplete
          value={filters.alternativo}
          onSelect={(codigo) => onChange({ alternativo: codigo })}
          onClear={() => onChange({ alternativo: "" })}
        />
        <select
          className={styles.select}
          value={filters.reprocesso}
          onChange={(e) => onChange({ reprocesso: e.target.value })}
          aria-label="Reprocesso"
        >
          <option value="">Reprocesso: todos</option>
          <option value="1">Só reprocesso</option>
          <option value="0">Sem reprocesso</option>
        </select>
        <select
          className={styles.select}
          value={filters.status}
          onChange={(e) => onChange({ status: e.target.value })}
          aria-label="Status de execução"
        >
          <option value="">Confirmada + planejada</option>
          <option value="confirmada">Só confirmada</option>
          <option value="planejada">Só planejada</option>
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
