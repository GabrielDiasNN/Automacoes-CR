import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { Search, Workflow } from "lucide-react";
import { useFocusTrap } from "../hooks/useFocusTrap";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { orchestratorApi, type Automation } from "../api/orchestrator";
import styles from "./CommandPalette.module.css";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  navItems: NavItem[];
}

type PaletteEntry =
  | { kind: "nav"; key: string; label: string; icon: ReactNode; to: string }
  | { kind: "automation"; key: string; label: string; automation: Automation };

/** Busca global (Ctrl+K) — pula direto para uma tela ou acha uma automação pelo nome. */
export function CommandPalette({ open, onClose, navItems }: CommandPaletteProps) {
  const navigate = useNavigate();
  const boxRef = useRef<HTMLDivElement>(null!);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const listboxId = useId();
  const debouncedQuery = useDebouncedValue(query, 250);
  const buscaAtiva = open && debouncedQuery.trim().length >= 2;

  useFocusTrap(boxRef, open, onClose);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setSelected(0);
    const id = requestAnimationFrame(() => inputRef.current?.focus());
    return () => cancelAnimationFrame(id);
  }, [open]);

  const fetchAutomations = useCallback(
    (signal?: AbortSignal) => orchestratorApi.listAutomations({ search: debouncedQuery.trim(), per_page: 5 }, signal),
    [debouncedQuery],
  );
  // Erro descartado deliberadamente (`?? []`): a paleta sem resultados de
  // automação ainda funciona para navegação por rota — não é um ErrorState
  // que caiba num popover de busca.
  const { data: automationResults } = useAsyncResource(buscaAtiva ? fetchAutomations : null, [debouncedQuery, open]);
  const automations = useMemo(() => automationResults ?? [], [automationResults]);

  const entries: PaletteEntry[] = useMemo(() => {
    const q = query.trim().toLowerCase();
    const navEntries: PaletteEntry[] = navItems
      .filter((n) => !q || n.label.toLowerCase().includes(q))
      .map((n) => ({ kind: "nav" as const, key: `nav-${n.to}`, label: n.label, icon: n.icon, to: n.to }));
    const autoEntries: PaletteEntry[] = automations.map((a) => ({
      kind: "automation" as const,
      key: `auto-${a.id}`,
      label: a.name,
      automation: a,
    }));
    return [...navEntries, ...autoEntries];
  }, [navItems, query, automations]);

  useEffect(() => {
    setSelected(0);
  }, [entries.length]);

  if (!open) return null;

  const activate = (entry: PaletteEntry) => {
    // `void`: `navigate` (react-router 7) devolve Promise que não interessa aqui.
    if (entry.kind === "nav") {
      void navigate(entry.to);
    } else {
      // Leva o nome escolhido para a tela de Automações, que rola até o card e
      // o destaca (antes: ia sempre para /automacoes, ignorando a automação).
      void navigate(`/automacoes?focus=${encodeURIComponent(entry.automation.name)}`);
    }
    onClose();
  };

  return createPortal(
    // Overlay de clique-fora do modal (padrão sem equivalente nativo).
    // Fecha só quando o próprio overlay é o alvo do evento — evita precisar
    // de stopPropagation no filho. Escape já fecha via useFocusTrap.
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions
    <div className={`overlay-scrim ${styles.overlay}`} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div
        ref={boxRef}
        className={`${styles.box} animate-in`}
        role="dialog"
        aria-modal="true"
        aria-label="Busca global"
      >
        <div className={styles.inputRow}>
          <Search size={15} className={styles.searchIcon} aria-hidden="true" />
          <input
            ref={inputRef}
            className={styles.input}
            placeholder="Ir para uma tela ou buscar automação…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setSelected((s) => Math.min(s + 1, entries.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setSelected((s) => Math.max(s - 1, 0));
              } else if (e.key === "Enter") {
                e.preventDefault();
                const entry = entries[selected];
                if (entry) activate(entry);
              }
            }}
            aria-label="Busca global"
            // `aria-activedescendant` só faz sentido semanticamente num
            // elemento com `role="combobox"` — sem isso o listbox abaixo não
            // é anunciado como as opções de UM combobox controlado por este
            // campo.
            role="combobox"
            aria-expanded={entries.length > 0}
            aria-controls={listboxId}
            aria-autocomplete="list"
            aria-activedescendant={entries[selected]?.key}
          />
          <kbd className={styles.kbd}>Esc</kbd>
        </div>

        {entries.length === 0 ? (
          <div className={styles.empty}>
            {debouncedQuery.trim().length >= 2 ? "Nenhum resultado." : "Digite para buscar telas e automações."}
          </div>
        ) : (
          <ul className={styles.list} role="listbox" id={listboxId}>
            {entries.map((entry, i) => (
              // `role="presentation"`: sem isso o <li> injeta um `listitem`
              // implícito entre o `listbox` e cada `option` — estrutura que
              // nenhum leitor de tela espera dentro de um combobox.
              <li key={entry.key} role="presentation">
                <button
                  id={`${listboxId}-${entry.key}`}
                  type="button"
                  className={`${styles.item} ${i === selected ? styles.itemActive : ""}`}
                  onMouseEnter={() => setSelected(i)}
                  onClick={() => activate(entry)}
                  role="option"
                  aria-selected={i === selected}
                >
                  <span className={styles.itemIcon}>{entry.kind === "nav" ? entry.icon : <Workflow size={15} />}</span>
                  <span className={styles.itemLabel}>{entry.label}</span>
                  {entry.kind === "automation" && <span className={styles.itemHint}>automação</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>,
    document.body,
  );
}
