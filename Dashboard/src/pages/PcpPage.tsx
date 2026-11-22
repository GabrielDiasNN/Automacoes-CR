import { useMemo, useState } from "react";
import { ClipboardList, RefreshCw, Search } from "lucide-react";
import {
  orchestratorApi,
  type PromovidaResumo,
  type PromovidaSnapshot,
} from "../api/orchestrator";
import {
  Button,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  FreshnessTag,
  Input,
  ListRow,
  Loading,
  Nameplate,
  Pager,
  StatTile,
  StatusTag,
  type Column,
} from "../components/ui";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { formatAge, formatNumber } from "../lib/format";
import page from "./page.module.css";
import styles from "./PcpPage.module.css";

const PAGE_SIZE = 25;
const STALE_THRESHOLD_MINUTES = 180;

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return formatNumber(value);
  return String(value);
}

function formatKpiLabel(key: string): string {
  if (key === "count") return "Total de linhas";
  const [op, col] = key.split(":");
  if (op && col) return `${op.toUpperCase()} · ${col}`;
  return key;
}

export function PcpPage() {
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [tablePage, setTablePage] = useState(1);

  const listRes = useAsyncResource<{ items: PromovidaResumo[] }>(
    (signal) => orchestratorApi.getPromovidas(signal),
    [],
  );

  const items = useMemo(() => listRes.data?.items ?? [], [listRes.data]);

  const activeItem = useMemo(() => {
    if (!items.length) return null;
    if (selectedSlug) {
      const found = items.find((item) => item.slug === selectedSlug);
      if (found) return found;
    }
    return items.find((item) => item.has_snapshot) ?? items[0] ?? null;
  }, [items, selectedSlug]);

  const activeSlug = activeItem?.slug ?? null;
  const shouldFetchSnapshot = Boolean(activeSlug && activeItem?.has_snapshot);

  const snapRes = useAsyncResource<PromovidaSnapshot | null>(
    shouldFetchSnapshot && activeSlug
      ? (signal) => orchestratorApi.getPromovidaLatest(activeSlug, signal)
      : null,
    [activeSlug, shouldFetchSnapshot],
  );

  const filteredRows = useMemo(() => {
    const rows = snapRes.data?.rows ?? [];
    const term = searchTerm.trim().toLowerCase();
    if (!term) return rows;
    return rows.filter((row) =>
      Object.values(row).some((val) => String(val ?? "").toLowerCase().includes(term)),
    );
  }, [snapRes.data, searchTerm]);

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE));
  const currentPage = Math.min(tablePage, totalPages);
  const pagedRows = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return filteredRows.slice(start, start + PAGE_SIZE);
  }, [filteredRows, currentPage]);

  const rowKeyMap = useMemo(
    () => new Map(pagedRows.map((row, index) => [row, `${currentPage}-${index}`])),
    [pagedRows, currentPage],
  );

  const columns = useMemo<Column<Record<string, unknown>>[]>(() => {
    const cols = snapRes.data?.columns ?? [];
    return cols.map((col) => ({
      key: col,
      header: col,
      render: (row) => formatCellValue(row[col]),
    }));
  }, [snapRes.data]);

  const handleSelect = (slug: string) => {
    setSelectedSlug(slug);
    setTablePage(1);
    setSearchTerm("");
  };

  return (
    <div className={page.page}>
      <Nameplate
        eyebrow="Análise · Consultas Promovidas (Snapshot-First)"
        title="PCP & Consultas"
        actions={
          <div className={page.toolbar}>
            <FreshnessTag lastUpdated={listRes.lastUpdated} error={listRes.error} />
            <Button
              size="sm"
              variant="subtle"
              onClick={() => {
                void listRes.refresh();
                if (shouldFetchSnapshot) void snapRes.refresh();
              }}
              disabled={listRes.loading || snapRes.loading}
              icon={<RefreshCw size={14} />}
            >
              Atualizar
            </Button>
          </div>
        }
      />

      {listRes.error && !listRes.data && <ErrorState message={listRes.error} />}
      {listRes.loading && !listRes.data && <Loading label="Carregando consultas promovidas" />}

      {items.length > 0 && (
        <div className={page.split}>
          <Card label="Catálogo ativo">
            <div className={page.list}>
              {items.map((item) => {
                const isSelected = item.slug === activeSlug;
                const stale =
                  item.has_snapshot &&
                  item.age_minutes !== null &&
                  item.age_minutes > STALE_THRESHOLD_MINUTES;
                return (
                  <ListRow
                    key={item.slug}
                    {...(isSelected
                      ? { tone: "var(--cyan)", "aria-current": "true" as const }
                      : stale
                        ? { tone: "var(--amber)" }
                        : {})}
                    onClick={() => handleSelect(item.slug)}
                    trailing={
                      <StatusTag tone={!item.has_snapshot ? "grey" : stale ? "amber" : "green"} dot>
                        {!item.has_snapshot
                          ? "sem snapshot"
                          : item.age_minutes !== null
                            ? formatAge(item.age_minutes * 60)
                            : "atual"}
                      </StatusTag>
                    }
                  >
                    <div>
                      <strong>{item.nome}</strong>
                      <div className={styles.metaLine}>
                        <span>modo {item.modo}</span>
                        {item.has_snapshot && (
                          <span>
                            {" · "}
                            {formatNumber(item.total_rows)} linhas · {formatNumber(item.excecoes_count)} exceções
                          </span>
                        )}
                      </div>
                    </div>
                  </ListRow>
                );
              })}
            </div>
          </Card>

          <div className={styles.stack}>
            {activeItem && !activeItem.has_snapshot && (
              <Card label={activeItem.titulo}>
                <EmptyState
                  icon={<ClipboardList size={28} />}
                  title="Nenhum snapshot gerado ainda"
                  hint={`Execute '${activeItem.slug}' no Orchestrator ou via run.ps1 -DryRun para popular esta visão sem consultar o Oracle em tempo real.`}
                />
              </Card>
            )}

            {activeItem && activeItem.has_snapshot && snapRes.loading && !snapRes.data && (
              <Loading label={`Carregando snapshot de ${activeItem.nome}`} />
            )}

            {snapRes.error && !snapRes.data && <ErrorState message={snapRes.error} />}

            {snapRes.data && (
              <>
                <Card
                  label={snapRes.data.titulo}
                  actions={
                    <StatusTag tone={snapRes.data.modo === "sombra" ? "amber" : "cyan"} dot>
                      modo {snapRes.data.modo}
                    </StatusTag>
                  }
                >
                  <div className={page.tiles}>
                    <StatTile
                      label="Linhas no snapshot"
                      value={formatNumber(snapRes.data.total_rows)}
                    />
                    <StatTile
                      label="Exceções detectadas"
                      value={formatNumber(snapRes.data.excecoes_count)}
                      tone={snapRes.data.excecoes_count > 0 ? "amber" : "green"}
                    />
                    {Object.entries(snapRes.data.kpis)
                      .filter(([key]) => key !== "count")
                      .map(([key, val]) => (
                        <StatTile
                          key={key}
                          label={formatKpiLabel(key)}
                          value={formatCellValue(val)}
                          big={false}
                        />
                      ))}
                  </div>
                </Card>

                <Card
                  label="Detalhamento do último snapshot"
                  actions={
                    <Input
                      value={searchTerm}
                      onChange={(e) => {
                        setSearchTerm(e.target.value);
                        setTablePage(1);
                      }}
                      placeholder="Filtrar linhas..."
                      aria-label="Filtrar linhas do snapshot"
                      icon={<Search size={14} />}
                    />
                  }
                >
                  {pagedRows.length === 0 ? (
                    <EmptyState
                      title="Nenhuma linha encontrada"
                      hint="Ajuste o filtro ou aguarde a próxima extração."
                    />
                  ) : (
                    <>
                      <DataTable
                        columns={columns}
                        rows={pagedRows}
                        rowKey={(row) => rowKeyMap.get(row) ?? ""}
                      />
                      {totalPages > 1 && (
                        <Pager
                          page={currentPage}
                          pages={totalPages}
                          currentPage={currentPage}
                          total={filteredRows.length}
                          itemLabel="linhas"
                          onPrev={() => setTablePage((p) => Math.max(1, p - 1))}
                          onNext={() => setTablePage((p) => Math.min(totalPages, p + 1))}
                        />
                      )}
                    </>
                  )}
                </Card>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
