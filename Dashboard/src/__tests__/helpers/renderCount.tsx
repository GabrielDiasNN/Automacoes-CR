import { useState, type ReactNode } from "react";
import { act, render } from "@testing-library/react";

/**
 * Helper para os testes de CONTAGEM DE RENDERS de `React.memo`.
 *
 * `renderSubject` roda no corpo de um pai a cada render — o elemento é recriado
 * a cada vez (como no app real), mas as PROPS devem vir de constantes estáveis
 * do teste. Cada teste injeta seu próprio "spy de corpo" (uma prop que o
 * componente invoca/lê durante o render — `columns[].render`, um getter em
 * `lines[0].label`, um mock de `formatNumber`/`toneVar`...) e afirma que o
 * contador NÃO sobe quando o pai re-renderiza: prova que o corpo do componente
 * memoizado não re-executou.
 *
 * (Um `<Profiler onRender>` NÃO serve aqui: ele dispara a cada commit de
 * ancestral mesmo quando o subtree memoizado deu bailout.)
 */
export function mountWithRerender(
  renderSubject: () => ReactNode,
  wrapper: (children: ReactNode) => ReactNode = (c) => c,
) {
  let rerender: () => void = () => {};

  function Parent() {
    const [, setN] = useState(0);
    rerender = () => setN((n) => n + 1);
    return <>{renderSubject()}</>;
  }

  const utils = render(<>{wrapper(<Parent />)}</>);

  return {
    ...utils,
    /** força um re-render do pai sem mudar nenhuma prop do subject. */
    rerenderParent: () => act(() => rerender()),
  };
}
