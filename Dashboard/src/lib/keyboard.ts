import type { KeyboardEvent } from "react";

/** Ativação por teclado de um elemento com `role="button"` que não é um
 *  `<button>` real (ex.: célula SVG, painel clicável). Enter e Espaço chamam
 *  `onActivate`, como um `<button>` faria. `preventDefault` evita que o Espaço
 *  role a página. */
export function onActivationKey(onActivate: () => void) {
  return (e: KeyboardEvent): void => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onActivate();
    }
  };
}
