import { useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { orchestratorApi } from "../../api/orchestrator";
import { useAsyncResource } from "../../hooks/useAsyncResource";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { IconButton, Input } from "../ui";
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
  const debouncedTerm = useDebouncedValue(term, 300);
  const containerRef = useRef<HTMLDivElement>(null);
  const termoValido = debouncedTerm.trim().length >= 2;

  useEffect(() => {
    if (!value) setSelectedLabel("");
  }, [value]);

  const fetchProdutos = useCallback(
    (signal?: AbortSignal) => orchestratorApi.getBeneficiamentoProdutos(debouncedTerm.trim(), signal),
    [debouncedTerm],
  );
  // Erro descartado deliberadamente (`?? []`): autocomplete sem sugestões é
  // uma UX aceitável para uma falha transitória de busca — não vale um
  // ErrorState dentro do dropdown.
  const { data } = useAsyncResource(termoValido ? fetchProdutos : null, [debouncedTerm]);
  const options = data?.items ?? [];

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
      <Input
        type="search"
        style={{ width: "100%" }}
        trailingPadding={26}
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
        <IconButton
          variant="plain"
          className={styles.clear}
          onClick={() => {
            onClear();
            setSelectedLabel("");
          }}
          aria-label="Limpar produto"
        >
          <X size={12} />
        </IconButton>
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
