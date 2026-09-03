import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Sem isso (achado nº 34, Onda 5), duas devDeps ficavam instaladas e nunca
// importadas (@testing-library/jest-dom, sem matchers nos testes) e o DOM de
// um teste vazava para o próximo (nenhum cleanup automático entre `it()`s
// que usam renderHook/render).
afterEach(() => {
  cleanup();
});
