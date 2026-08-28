import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { Search, Workflow } from "lucide-react";
import { useFocusTrap } from "../hooks/useFocusTrap";
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
  const [automations, setAutomations] = useState<Automation[]>([]);
  const debouncedQuery = useDebouncedValue(query, 250);

  useFocusTrap(boxRef, open, onClose);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setSelected(0);
    setAutomations([]);
    const id = requestAnimationFrame(() => inputRef.current?.focus());
    return () => cancelAnimationFrame(id);
  }, [open]);

  useEffect(() => {
    if (!open || debouncedQuery.trim().length < 2) {
      setAutomations([]);
      return;
    }
    let cancelled = false;
    orchestratorApi
      .listAutomations({ search: debouncedQuery.trim(), per_page: 5 })
      .then((items) => {
        if (!cancelled) setAutomations(items);
      })
      .catch(() => {
        if (!cancelled) setAutomations([]);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, open]);

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
    if (entry.kind === "nav") {
      navigate(entry.to);
    } else {
      // Leva o nome escolhido para a tela de Automações, que rola até o card e
      // o destaca (antes: ia sempre para /automacoes, ignorando a automação).
      navigate(`/automacoes?focus=${encodeURIComponent(entry.automation.name)}`);
    }
    onClose();
  };

  return createPortal(
    <div className={styles.overlay} onMouseDown={onClose}>
      <div
        ref={boxRef}
        className={`${styles.box} animate-in`}
        role="dialog"
        aria-modal="true"
        aria-label="Busca global"
        onMouseDown={(e) => e.stopPropagation()}
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
            aria-activedescendant={entries[selected]?.key}
          />
          <kbd className={styles.kbd}>Esc</kbd>
        </div>

        {entries.length === 0 ? (
          <div className={styles.empty}>
            {debouncedQuery.trim().length >= 2 ? "Nenhum resultado." : "Digite para buscar telas e automações."}
          </div>
        ) : (
          <ul className={styles.list} role="listbox">
            {entries.map((entry, i) => (
              <li key={entry.key}>
                <button
                  id={entry.key}
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
