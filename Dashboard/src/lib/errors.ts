/** Extrai uma mensagem legível de um valor capturado em `catch`.
 *  Padrão `e instanceof Error ? e.message : String(e)` repetido em 11 pontos
 *  do app antes desta extração (achado nº 22, Onda 4). */
export function errMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
