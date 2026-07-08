import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { orchestratorApi, type BeneficiamentoProdutoOption } from "../../api/orchestrator";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import styles from "./ProductAutocomplete.module.css";

interface ProductAutocompleteProps {
  value: string;
  onSelect: (codigo: string, label: string) => void;
  onClear: () => void;
}

/** Busca de produto por código/descrição (596+ itens — inviável em `<select>`). */
export function ProductAutocomplete({ value, onSelect, onClear }: ProductAutocompleteProps) {
  const [term, setTerm] = useState("");
  const [selectedLabel, setSelectedLabel] = useState("");
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<BeneficiamentoProdutoOption[]>([]);
  const debouncedTerm = useDebouncedValue(term, 300);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!value) setSelectedLabel("");
  }, [value]);

  useEffect(() => {
    if (debouncedTerm.trim().length < 2) {
      setOptions([]);
      return undefined;
    }
    let cancelled = false;
    orchestratorApi
      .getBeneficiamentoProdutos(debouncedTerm.trim())
      .then((res) => {
        if (!cancelled) setOptions(res.items);
      })
      .catch(() => {
        if (!cancelled) setOptions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedTerm]);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const displayValue = open ? term : selectedLabel || value;

  return (
    <div className={styles.wrap} ref={containerRef}>
      <input
        type="search"
        className={styles.input}
        placeholder="Buscar produto (código ou nome)…"
        value={displayValue}
        onChange={(e) => {
          setTerm(e.target.value);
          setOpen(true);
        }}
        onFocus={() => {
          setTerm("");
          setOpen(true);
        }}
        aria-label="Produto"
      />
      {value && !open && (
        <button
          type="button"
          className={styles.clear}
          onClick={() => {
            onClear();
            setSelectedLabel("");
          }}
          aria-label="Limpar produto"
        >
          <X size={12} />
        </button>
      )}
      {open && options.length > 0 && (
        <ul className={styles.dropdown} role="listbox">
          {options.map((item) => (
            <li key={item.codigo ?? item.produto}>
              <button
                type="button"
                className={styles.option}
                onClick={() => {
                  const codigo = item.codigo ?? "";
                  const label = `${codigo} — ${item.produto}`;
                  onSelect(codigo, label);
                  setSelectedLabel(label);
                  setTerm("");
                  setOpen(false);
                }}
              >
                <span className={styles.code}>{item.codigo ?? "—"}</span>
                <span className={styles.name}>{item.produto}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
