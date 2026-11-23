import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  ArrowUpDown,
  ClipboardList,
  Download,
  FileSpreadsheet,
  History,
  Image as ImageIcon,
  Info,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Search,
  Star,
  Table2,
  Zap,
} from "lucide-react";
import {
  orchestratorApi,
  type Automation,
  type PromovidaHistoricoItem,
  type PromovidaResumo,
  type PromovidaSnapshot,
} from "../api/orchestrator";
import {
  Button,
  Card,
  ConfirmModal,
  DataTable,
  EmptyState,
  ErrorState,
  FreshnessTag,
  Input,
  ListRow,
  Loading,
  Nameplate,
  Pager,
  Select,
  StatTile,
  StatusTag,
  Tabs,
  type Column,
  type TabItem,
} from "../components/ui";
import { CardGallery } from "../components/CardGallery";
import { PcpAboutTab } from "../components/pcp/PcpAboutTab";
import {
  exportRowsAsCsv,
  exportRowsAsExcel,
  formatCellValue,
  formatColumnHeader,
  formatKpiLabel,
} from "../components/pcp/PcpExportUtils";
import { useAction } from "../hooks/useAction";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { formatAge, formatNumber } from "../lib/format";
import page from "./page.module.css";
import styles from "./PcpPage.module.css";

const PAGE_SIZE = 25;
const STALE_THRESHOLD_MINUTES = 180;

type OriginFilter = "all" | "automacao" | "promovida";
type DetailTab = "dados" | "cards" | "historico" | "sobre";

const PINNED_STORAGE_KEY = "pcp_pinned_slugs";

function readPinnedSlugs(): string[] {
  try {
    const raw = localStorage.getItem(PINNED_STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

const HISTORY_COLUMNS: Column<PromovidaHistoricoItem>[] = [
  { key: "generated_at", header: "Gerado em", render: (r) => r.generated_at },
  { key: "modo", header: "Modo", render: (r) => r.modo },
  { key: "total_rows", header: "Registros", align: "right", render: (r) => formatNumber(r.total_rows) },
  { key: "excecoes_count", header: "Exceções", align: "right", render: (r) => formatNumber(r.excecoes_count) },
];

export function PcpPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const slugParam = searchParams.get("slug");
  const [selectedSlug, setSelectedSlug] = useState<string | null>(() => slugParam);

  useEffect(() => {
    if (slugParam) {
      setSelectedSlug(slugParam);
      setTablePage(1);
      setSearchTerm("");
      setColFilterKey("");
      setColFilterVal("");
      setSortCol(null);
      setDetailTab("dados");
    }
  }, [slugParam]);
  const [originFilter, setOriginFilter] = useState<OriginFilter>("all");
  const [catalogSearch, setCatalogSearch] = useState("");
  const [catalogCollapsed, setCatalogCollapsed] = useState(false);
  const [pinnedSlugs, setPinnedSlugs] = useState<string[]>(() => readPinnedSlugs());
  const [searchTerm, setSearchTerm] = useState("");
  const [colFilterKey, setColFilterKey] = useState("");
  const [colFilterVal, setColFilterVal] = useState("");
  const [tablePage, setTablePage] = useState(1);
  const [detailTab, setDetailTab] = useState<DetailTab>("dados");
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [confirmDispatch, setConfirmDispatch] = useState<Automation | null>(null);
  const { busyKey, run } = useAction<string>();

  const togglePin = (slug: string) => {
    setPinnedSlugs((prev) => {
      const next = prev.includes(slug) ? prev.filter((s) => s !== slug) : [slug, ...prev];
      try {
        localStorage.setItem(PINNED_STORAGE_KEY, JSON.stringify(next));
      } catch {
        /* ignora cota de storage */
      }
      return next;
    });
  };

  const listRes = useAsyncResource<{ items: PromovidaResumo[] }>(
    (signal) => orchestratorApi.getPromovidas(signal),
    [],
  );

  const autosRes = useAsyncResource<Automation[]>(
    (signal) => orchestratorApi.listAllAutomations(signal).catch(() => []),
    [],
  );

  const items = useMemo(() => listRes.data?.items ?? [], [listRes.data]);

  const filteredCatalog = useMemo(() => {
    const q = catalogSearch.trim().toLowerCase();
    const pinnedSet = new Set(pinnedSlugs);
    const list = items.filter((item) => {
      if (originFilter !== "all" && (item.origem ?? "promovida") !== originFilter) return false;
      if (!q) return true;
      return (
        item.nome.toLowerCase().includes(q) ||
        item.titulo.toLowerCase().includes(q) ||
        (item.codigo ?? "").toLowerCase().includes(q) ||
        (item.setor ?? "").toLowerCase().includes(q)
      );
    });
    return [...list].sort((a, b) => Number(pinnedSet.has(b.slug)) - Number(pinnedSet.has(a.slug)));
  }, [items, originFilter, catalogSearch, pinnedSlugs]);

  const activeItem = useMemo(() => {
    if (!items.length) return null;
    if (selectedSlug) {
      const found = items.find((item) => item.slug === selectedSlug);
      if (found) return found;
    }
    return filteredCatalog.find((item) => item.has_snapshot) ?? filteredCatalog[0] ?? items[0] ?? null;
  }, [items, filteredCatalog, selectedSlug]);

  const activeSlug = activeItem?.slug ?? null;
  const shouldFetchSnapshot = Boolean(activeSlug && activeItem?.has_snapshot);

  const linkedAutomation = useMemo(() => {
    if (!activeItem) return null;
    const autos = autosRes.data ?? [];
    const targetName = (activeItem.automation_name ?? activeItem.nome).toLowerCase();
    return autos.find((a) => a.name.toLowerCase() === targetName) ?? null;
  }, [activeItem, autosRes.data]);

  const snapRes = useAsyncResource<PromovidaSnapshot | null>(
    shouldFetchSnapshot && activeSlug
      ? (signal) => orchestratorApi.getPromovidaLatest(activeSlug, signal)
      : null,
    [activeSlug, shouldFetchSnapshot],
  );
  const activeSnap = snapRes.data && snapRes.data.slug === activeSlug ? snapRes.data : null;

  const histRes = useAsyncResource<{ slug: string; items: PromovidaHistoricoItem[] } | null>(
    detailTab === "historico" && activeSlug
      ? (signal) => orchestratorApi.getPromovidaHistory(activeSlug, 30, signal)
      : null,
    [activeSlug, detailTab],
  );
  const activeHist = histRes.data && histRes.data.slug === activeSlug ? histRes.data : null;

  const distinctColumnValues = useMemo(() => {
    if (!colFilterKey) return [];
    const rows = activeSnap?.rows ?? [];
    const set = new Set<string>();
    for (const row of rows) {
      const v = row[colFilterKey];
      if (v !== null && v !== undefined && String(v).trim() !== "") set.add(String(v));
    }
    return [...set].sort((a, b) => a.localeCompare(b, "pt-BR", { numeric: true })).slice(0, 120);
  }, [activeSnap, colFilterKey]);

  const filteredRows = useMemo(() => {
    const rows = activeSnap?.rows ?? [];
    const term = searchTerm.trim().toLowerCase();
    const matched = rows.filter((row) => {
      if (colFilterKey && colFilterVal && String(row[colFilterKey] ?? "") !== colFilterVal) return false;
      if (!term) return true;
      return Object.values(row).some((val) => String(val ?? "").toLowerCase().includes(term));
    });
    if (!sortCol) return matched;
    return [...matched].sort((a, b) => {
      const va = a[sortCol];
      const vb = b[sortCol];
      if (va === vb) return 0;
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      const cmp =
        typeof va === "number" && typeof vb === "number"
          ? va - vb
          : String(va).localeCompare(String(vb), "pt-BR", { numeric: true });
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [activeSnap, searchTerm, colFilterKey, colFilterVal, sortCol, sortDir]);

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
    const cols = activeSnap?.columns ?? [];
    return cols.map((col) => ({
      key: col,
      header: (
        <button
          type="button"
          className={styles.sortBtn}
          onClick={() => {
            if (sortCol === col) {
              setSortDir((d) => (d === "asc" ? "desc" : "asc"));
            } else {
              setSortCol(col);
              setSortDir("asc");
            }
          }}
        >
          <span>{formatColumnHeader(col)}</span>
          <ArrowUpDown size={11} aria-hidden="true" />
        </button>
      ),
      render: (row) => formatCellValue(row[col]),
    }));
  }, [activeSnap, sortCol]);

  const handleSelect = (slug: string) => {
    setSelectedSlug(slug);
    setSearchParams({ slug }, { replace: true });
    setTablePage(1);
    setSearchTerm("");
    setColFilterKey("");
    setColFilterVal("");
    setSortCol(null);
    setDetailTab("dados");
  };

  const countAutomacoes = useMemo(() => items.filter((i) => i.origem === "automacao").length, [items]);
  const countPromovidas = useMemo(() => items.filter((i) => (i.origem ?? "promovida") === "promovida").length, [items]);
  const cards = activeSnap?.cards ?? [];

  const detailTabs: TabItem<DetailTab>[] = [
    { id: "dados", label: "Tabela de Dados", icon: <Table2 size={14} />, badge: filteredRows.length },
    { id: "cards", label: "Cards Visuais PNG", icon: <ImageIcon size={14} />, badge: cards.length || undefined },
    { id: "historico", label: "Histórico", icon: <History size={14} /> },
    { id: "sobre", label: "Sobre / Regra de Negócio", icon: <Info size={14} /> },
  ];

  return (
    <div className={page.page}>
      <Nameplate
        eyebrow="Gestão & BI · Automações + Consultas Promovidas"
        title="Central de Consultas & PCP"
        actions={
          <div className={page.toolbar}>
            <FreshnessTag lastUpdated={listRes.lastUpdated} error={listRes.error} />
            <Button
              size="sm"
              variant="subtle"
              icon={catalogCollapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
              onClick={() => setCatalogCollapsed((v) => !v)}
              aria-pressed={catalogCollapsed}
            >
              {catalogCollapsed ? "Mostrar catálogo" : "Recolher catálogo"}
            </Button>
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
      {listRes.loading && !listRes.data && <Loading label="Carregando central de consultas" />}

      {items.length > 0 && (
        <div className={`${styles.layout} ${catalogCollapsed ? styles.layoutCollapsed : ""}`}>
          {!catalogCollapsed && (
            <Card label="Catálogo ativo">
              <div className={styles.catalogTools}>
                <Input
                  value={catalogSearch}
                  onChange={(e) => setCatalogSearch(e.target.value)}
                  placeholder="Buscar por código, nome ou setor…"
                  aria-label="Buscar no catálogo de consultas"
                  icon={<Search size={14} />}
                />
                <div className={styles.filterPills} role="group" aria-label="Filtrar por origem">
                  <button
                    type="button"
                    className={`${styles.pill} ${originFilter === "all" ? styles.pillActive : ""}`}
                    onClick={() => setOriginFilter("all")}
                  >
                    Todas ({items.length})
                  </button>
                  {countAutomacoes > 0 && (
                    <button
                      type="button"
                      className={`${styles.pill} ${originFilter === "automacao" ? styles.pillActive : ""}`}
                      onClick={() => setOriginFilter("automacao")}
                    >
                      Automações ({countAutomacoes})
                    </button>
                  )}
                  <button
                    type="button"
                    className={`${styles.pill} ${originFilter === "promovida" ? styles.pillActive : ""}`}
                    onClick={() => setOriginFilter("promovida")}
                  >
                    Promovidas ({countPromovidas})
                  </button>
                </div>
              </div>

              <div className={page.list}>
                {filteredCatalog.map((item) => {
                  const isSelected = item.slug === activeSlug;
                  const isPinned = pinnedSlugs.includes(item.slug);
                  const stale =
                    item.has_snapshot &&
                    item.age_minutes !== null &&
                    item.age_minutes > STALE_THRESHOLD_MINUTES;
                  return (
                    <div key={item.slug} className={styles.catalogRow}>
                      <ListRow
                        className={styles.catalogRowMain}
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
                          <div className={styles.itemHead}>
                            {item.codigo && <span className={styles.itemCode}>{item.codigo}</span>}
                            <strong>{item.nome}</strong>
                          </div>
                          <div className={styles.metaLine}>
                            <span>{item.setor ?? `modo ${item.modo}`}</span>
                            {item.has_snapshot && (
                              <span>
                                {" · "}
                                {formatNumber(item.total_rows)} reg. · {formatNumber(item.excecoes_count)} exc.
                              </span>
                            )}
                          </div>
                        </div>
                      </ListRow>
                      <button
                        type="button"
                        className={`${styles.pinBtn} ${isPinned ? styles.pinActive : ""}`}
                        onClick={() => togglePin(item.slug)}
                        aria-label={`${isPinned ? "Desafixar" : "Fixar"} ${item.nome} nos favoritos`}
                        aria-pressed={isPinned}
                        title={isPinned ? "Remover dos favoritos" : "Fixar no topo"}
                      >
                        <Star size={14} fill={isPinned ? "currentColor" : "none"} />
                      </button>
                    </div>
                  );
                })}
                {filteredCatalog.length === 0 && (
                  <EmptyState
                    title="Nenhuma consulta encontrada"
                    hint="Ajuste o filtro ou a busca do catálogo."
                  />
                )}
              </div>
            </Card>
          )}

          <div className={styles.stack}>
            {activeItem && !activeItem.has_snapshot && (
              <Card
                label={activeItem.titulo}
                actions={
                  linkedAutomation ? (
                    <Button
                      size="sm"
                      variant="primary"
                      icon={<Zap size={13} />}
                      disabled={busyKey === linkedAutomation.name || !linkedAutomation.enabled}
                      onClick={() => setConfirmDispatch(linkedAutomation)}
                    >
                      Disparar agora
                    </Button>
                  ) : undefined
                }
              >
                <EmptyState
                  icon={<ClipboardList size={28} />}
                  title="Nenhum snapshot gerado ainda"
                  hint={`Execute '${activeItem.slug}' no Orchestrator ou via run.ps1 -DryRun para popular esta visão sem consultar o Oracle em tempo real.`}
                />
              </Card>
            )}

            {activeItem && activeItem.has_snapshot && snapRes.loading && !activeSnap && (
              <Loading label={`Carregando snapshot de ${activeItem.nome}`} />
            )}

            {snapRes.error && !activeSnap && <ErrorState message={snapRes.error} />}

            {activeSnap && (
              <>
                <Card
                  label={activeSnap.titulo}
                  actions={
                    <div className={page.toolbar}>
                      <StatusTag tone={activeSnap.modo === "sombra" ? "amber" : "cyan"} dot>
                        {activeSnap.origem === "automacao" ? "automação" : `modo ${activeSnap.modo}`}
                      </StatusTag>
                      {activeSnap.columns.length > 0 && filteredRows.length > 0 && (
                        <>
                          <Button
                            size="sm"
                            variant="subtle"
                            icon={<Download size={13} />}
                            onClick={() =>
                              exportRowsAsCsv(activeSnap.slug, activeSnap.columns, filteredRows)
                            }
                          >
                            Exportar CSV
                          </Button>
                          <Button
                            size="sm"
                            variant="subtle"
                            icon={<FileSpreadsheet size={13} />}
                            onClick={() =>
                              exportRowsAsExcel(activeSnap.slug, activeSnap.columns, filteredRows)
                            }
                          >
                            Exportar Excel
                          </Button>
                        </>
                      )}
                      {linkedAutomation && (
                        <Button
                          size="sm"
                          variant="primary"
                          icon={<Zap size={13} />}
                          disabled={busyKey === linkedAutomation.name || !linkedAutomation.enabled}
                          onClick={() => setConfirmDispatch(linkedAutomation)}
                        >
                          Atualizar dados
                        </Button>
                      )}
                    </div>
                  }
                >
                  <div className={page.tiles}>
                    <StatTile
                      label="Linhas no snapshot"
                      value={formatNumber(activeSnap.total_rows)}
                    />
                    <StatTile
                      label="Exceções detectadas"
                      value={formatNumber(activeSnap.excecoes_count)}
                      tone={activeSnap.excecoes_count > 0 ? "amber" : "green"}
                    />
                    {Object.entries(activeSnap.kpis)
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

                <Tabs
                  items={detailTabs}
                  activeId={detailTab}
                  onChange={setDetailTab}
                  ariaLabel="Visões do snapshot selecionado"
                />

                {detailTab === "dados" && (
                  <Card
                    label="Detalhamento do último snapshot"
                    actions={
                      <div className={styles.tableTools}>
                        {activeSnap.columns.length > 0 && (
                          <Select
                            aria-label="Filtrar por coluna"
                            value={colFilterKey}
                            onChange={(e) => {
                              setColFilterKey(e.target.value);
                              setColFilterVal("");
                              setTablePage(1);
                            }}
                          >
                            <option value="">Todas as colunas</option>
                            {activeSnap.columns.map((col) => (
                              <option key={col} value={col}>
                                {formatColumnHeader(col)}
                              </option>
                            ))}
                          </Select>
                        )}
                        {colFilterKey && distinctColumnValues.length > 0 && (
                          <Select
                            aria-label="Valor da coluna"
                            value={colFilterVal}
                            onChange={(e) => {
                              setColFilterVal(e.target.value);
                              setTablePage(1);
                            }}
                          >
                            <option value="">Todos os valores</option>
                            {distinctColumnValues.map((val) => (
                              <option key={val} value={val}>
                                {val}
                              </option>
                            ))}
                          </Select>
                        )}
                        <Input
                          value={searchTerm}
                          onChange={(e) => {
                            setSearchTerm(e.target.value);
                            setTablePage(1);
                          }}
                          placeholder="Filtrar linhas…"
                          aria-label="Filtrar linhas do snapshot"
                          icon={<Search size={14} />}
                        />
                      </div>
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
                )}

                {detailTab === "cards" && (
                  <Card label="Cards visuais gerados (PNG)">
                    <CardGallery slug={activeSnap.slug} cards={cards} />
                  </Card>
                )}

                {detailTab === "historico" && (
                  <Card label="Histórico recente de snapshots">
                    {histRes.error && !activeHist ? (
                      <ErrorState message={histRes.error} />
                    ) : histRes.loading && !activeHist ? (
                      <Loading label="Carregando histórico" />
                    ) : (activeHist?.items ?? []).length === 0 ? (
                      <EmptyState
                        title="Sem histórico registrado"
                        hint="O histórico é gravado em promovidas.db a cada execução das consultas promovidas."
                      />
                    ) : (
                      <DataTable
                        columns={HISTORY_COLUMNS}
                        rows={activeHist?.items ?? []}
                        rowKey={(r) => `${r.slug}-${r.generated_at}`}
                      />
                    )}
                  </Card>
                )}

                {detailTab === "sobre" && activeItem && (
                  <PcpAboutTab
                    item={activeItem}
                    snapshot={activeSnap}
                    linkedAutomation={linkedAutomation}
                  />
                )}
              </>
            )}
          </div>
        </div>
      )}

      <ConfirmModal
        open={!!confirmDispatch}
        title="Disparar atualização"
        message={`Enfileirar "${confirmDispatch?.name ?? ""}" agora no Orchestrator para atualizar os dados?`}
        confirmLabel="Disparar"
        onConfirm={() => {
          if (!confirmDispatch) return;
          const auto = confirmDispatch;
          setConfirmDispatch(null);
          void run(auto.name, () => orchestratorApi.startAutomation(auto.id), {
            fallbackMessage: `${auto.name} enfileirada`,
            onDone: () => {
              void listRes.refresh();
              if (shouldFetchSnapshot) void snapRes.refresh();
            },
            invalidate: ["overview", "health"],
          });
        }}
        onCancel={() => setConfirmDispatch(null)}
      />
    </div>
  );
}
