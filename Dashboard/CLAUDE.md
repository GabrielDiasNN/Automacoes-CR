# Dashboard — contexto de módulo

Carregado apenas ao trabalhar em `Dashboard/`. As regras universais (encoding, caminhos, Zero-Trust, commits, E2E) estão no `CLAUDE.md` da raiz.

## Comandos

O Dashboard tem toolchain próprio em `Dashboard/` (lockfile, ESLint, Vitest, Vite) — o `package.json` da raiz só delega. Todo comando roda com `--prefix Dashboard` ou a partir dessa pasta, e os quatro abaixo são exatamente o job `frontend` do CI (bloqueante quando o diff toca `.js`/`.ts`/`.tsx`).
```powershell
npm ci --prefix Dashboard              # instalar pelo lockfile
npm run lint --prefix Dashboard        # ESLint
npm run test:coverage --prefix Dashboard  # Vitest com gate de cobertura
npm run build --prefix Dashboard       # tsc + vite → Dashboard/dist/ (servido pelo FastAPI)

# Um único arquivo/teste de front
npm run test --prefix Dashboard -- src/components/Foo.test.tsx -t "nome do teste"
```

## Design — padrões a evitar

A identidade está em `src/styles/tokens.css` (grafite + sistema de sinais, IBM Plex self-hosted, tabelas densas com `TableDensityContext`). Ao criar ou alterar UI, evite:

- Cor decorativa ou hex literal fora dos tokens: cor aqui é sinal (status, severidade), nunca enfeite.
- Gradientes, glassmorphism e sombras pesadas como ornamento (única exceção: a textura `.hazard`, só em zonas que exigem atenção do operador).
- Emoji como ícone ou indicador de status.
- Trocar a família IBM Plex por fonte genérica, ou carregar fonte/CDN externo (a rede interna não depende de CDN).
- "Card para tudo": dado tabular vai em tabela densa, não em grade de cards.
