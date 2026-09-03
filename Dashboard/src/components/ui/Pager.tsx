import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "./Button";
import styles from "./Pager.module.css";

interface PagerProps {
  page: number;
  pages: number;
  /** total de itens — some no rótulo quando informado. */
  total?: number;
  /** ex.: "execuções", "registros" — concatenado com `total`. */
  itemLabel?: string;
  onPrev: () => void;
  onNext: () => void;
}

/** Paginação Anterior/Próxima — dois componentes de botão e duas grafias do
 *  separador ("/" vs "de") coexistiam para a mesma semântica em
 *  `ExecucoesPage` e `DetailDrawer` (achado nº 15, Onda 4). */
export function Pager({ page, pages, total, itemLabel, onPrev, onNext }: PagerProps) {
  return (
    <div className={styles.wrap}>
      <Button size="sm" variant="subtle" icon={<ChevronLeft size={14} />} disabled={page <= 1} onClick={onPrev}>
        Anterior
      </Button>
      <span className={styles.label}>
        página {page} / {pages}
        {total != null && itemLabel ? ` · ${total} ${itemLabel}` : ""}
      </span>
      <Button size="sm" variant="subtle" onClick={onNext} disabled={page >= pages}>
        Próxima <ChevronRight size={14} />
      </Button>
    </div>
  );
}
