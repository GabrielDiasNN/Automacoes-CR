export interface VirtualWindow {
  /** índice da primeira linha a renderizar (inclusive). */
  start: number;
  /** índice logo após a última linha a renderizar (exclusive). */
  end: number;
  /** altura do espaçador acima das linhas renderizadas, em px. */
  topPad: number;
  /** altura do espaçador abaixo, em px. */
  bottomPad: number;
}

/**
 * Janela de virtualização por altura de linha FIXA (estimada). Para uma lista
 * de `total` itens de altura `rowH` px num viewport de `viewportH` px rolado a
 * `scrollTop` px, devolve o intervalo `[start, end)` visível (mais `overscan`
 * linhas de folga em cada ponta) e a altura dos dois espaçadores que preservam
 * a barra de rolagem.
 *
 * `rowH` é uma estimativa — o console mantém `white-space: pre-wrap`, então uma
 * linha de log muito longa ocupa mais de uma linha visual e o espaçador fica
 * alguns px impreciso. Aceitável: a esmagadora maioria das linhas cabe em uma
 * linha visual e o overscan absorve o erro sem buraco visível.
 */
export function computeWindow(
  scrollTop: number,
  rowH: number,
  viewportH: number,
  total: number,
  overscan: number,
): VirtualWindow {
  if (total <= 0 || rowH <= 0) {
    return { start: 0, end: 0, topPad: 0, bottomPad: 0 };
  }
  const clampedTop = Math.max(0, Math.min(scrollTop, total * rowH));
  const firstVisible = Math.floor(clampedTop / rowH);
  const lastVisible = Math.ceil((clampedTop + viewportH) / rowH);
  const start = Math.max(0, firstVisible - overscan);
  const end = Math.min(total, Math.max(start, lastVisible + overscan));
  return {
    start,
    end,
    topPad: start * rowH,
    bottomPad: Math.max(0, (total - end) * rowH),
  };
}
