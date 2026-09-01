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
