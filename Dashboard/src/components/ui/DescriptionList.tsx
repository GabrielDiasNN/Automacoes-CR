import type { ReactNode } from "react";
import styles from "./DescriptionList.module.css";

/** Grade de pares chave/valor (`<dl>`) — o componente `KV` estava copiado
 *  inteiro em `SystemPage.tsx` e `ExecucoesPage.ExecDetailBody.tsx`,
 *  divergindo só no `fontFamily` do valor (achado nº 13, Onda 4). */
export function DescriptionList({ children }: { children: ReactNode }) {
  return <dl className={styles.list}>{children}</dl>;
}

export function KeyValue({ k, v }: { k: string; v: ReactNode }) {
  return (
    <>
      <dt className={styles.term}>{k}</dt>
      <dd className={styles.value}>{v}</dd>
    </>
  );
}
