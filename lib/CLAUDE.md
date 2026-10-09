# lib — contexto de módulo

Carregado apenas ao trabalhar em `lib/`. As regras universais estão no `CLAUDE.md` da raiz.

## Testes PowerShell (Pester 5.7.1)

Gate bloqueante no CI sempre que o diff toca `.ps1`/`.psm1` **ou** `.js` (as travas anti-regressão do WhatsApp em `lib/tests` protegem arquivos JS).
```powershell
Import-Module Pester -RequiredVersion 5.7.1 -Force
Invoke-Pester -Path .\lib\tests -CI
Invoke-Pester -Path .\lib\tests\Lib-Config.Tests.ps1   # arquivo único
```

## Dependências Node (motor WhatsApp)

- `postinstall` = `node scripts/aplicar-patches.js`: aplica `lib/patches/*.patch` sem dependências e é idempotente. O `patch-package` saiu porque sua cadeia (braces/micromatch, CVE-2026-93687) não tem correção publicada.
- `extract-zip` é o fork em `lib/vendor/extract-zip` (`2.0.2-automacoes.1`, corrige CVE-2026-19693 e CVE-2026-56876) via override `file:../../../vendor/extract-zip`. O npm resolve esse `file:` relativo à pasta do pacote dependente (`node_modules/@puppeteer/browsers/`), não à raiz de `lib/`: por isso `file:vendor/extract-zip` quebra a regeneração com ENOENT.
- Regenerar o lock: copie `lib/` sem `node_modules` para uma pasta temporária, remova o nó `node_modules/extract-zip` do `package-lock.json` da cópia, rode `npm install --package-lock-only --ignore-scripts` e confira `version` `2.0.2-automacoes.1` e `resolved` `file:vendor/extract-zip`. Se reresolver outro caminho, restaure o bloco anterior do lock.
- `tests/lib-dependencias.test.js` guarda `package.json` e lock (sem patch-package, fork do extract-zip, whatsapp-web.js 1.34.7, basic-ftp >= 6.2.1) sem rede. Roda em `npm test` dentro de `lib/` (gate de cobertura 90%).
