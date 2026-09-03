import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "./Button";
import styles from "./Pager.module.css";

interface PagerProps {
  /** Exibido no rótulo "página X / Y" — normalmente o eco do servidor
   *  (`data.page`), mais preciso para o que está de fato na tela. */
  page: number;
  pages: number;
  /** Estado de controle local (o que o próximo clique vai incrementar/
   *  decrementar — ex.: `pageNum` em `ExecucoesPage`), usado para habilitar/
   *  desabilitar os botões. Quando omitido, cai em `page`.
   *
   *  Separado de `page` de propósito: `page` (eco do servidor) atrasa em
   *  relação ao clique enquanto uma requisição está em voo ou enquanto
   *  `usePolling` está em backoff de 429 (`data` congelado por até a janela
   *  do `Retry-After`) — nessa janela, `page <= 1`/`page >= pages` decide
   *  com um valor desatualizado. Dois cliques rápidos em "Próxima" antes da
   *  primeira resposta chegar podiam levar `pageNum` além de `pages`,
   *  pedindo uma página fora do intervalo (achado de revisão de código). */
  currentPage?: number;
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
export function Pager({ page, pages, currentPage, total, itemLabel, onPrev, onNext }: PagerProps) {
  const controlPage = currentPage ?? page;
  return (
    <div className={styles.wrap}>
      <Button size="sm" variant="subtle" icon={<ChevronLeft size={14} />} disabled={controlPage <= 1} onClick={onPrev}>
        Anterior
      </Button>
      <span className={styles.label}>
        página {page} / {pages}
        {total != null && itemLabel ? ` · ${total} ${itemLabel}` : ""}
      </span>
      <Button size="sm" variant="subtle" onClick={onNext} disabled={controlPage >= pages}>
        Próxima <ChevronRight size={14} />
      </Button>
    </div>
  );
}
