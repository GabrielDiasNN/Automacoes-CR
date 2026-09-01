# lib — contexto de módulo

Carregado apenas ao trabalhar em `lib/`. As regras universais estão no `CLAUDE.md` da raiz.

## Testes PowerShell (Pester 5.7.1)

Gate bloqueante no CI sempre que o diff toca `.ps1`/`.psm1` **ou** `.js` (as travas anti-regressão do WhatsApp em `lib/tests` protegem arquivos JS).
```powershell
Import-Module Pester -RequiredVersion 5.7.1 -Force
Invoke-Pester -Path .\lib\tests -CI
Invoke-Pester -Path .\lib\tests\Lib-Config.Tests.ps1   # arquivo único
```
