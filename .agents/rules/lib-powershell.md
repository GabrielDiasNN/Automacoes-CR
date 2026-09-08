# Regra de Workspace: Bibliotecas PowerShell e Infraestrutura

Aplica-se a arquivos em `lib/`, `Infrastructure/` e scripts PowerShell (`.ps1`, `.psm1`).

## Regras Críticas de Encoding e Caminhos

- **Encoding Obrigatório**: Todos os arquivos `.ps1` e `.psm1` devem ser salvos rigorosamente em **UTF-8 with BOM**.
- **Caminhos Relativos**: É terminantemente proibido o uso de caminhos absolutos (ex.: `C:\...`). Utilize sempre caminhos relativos à raiz (`.\`) ou `$PSScriptRoot`.

## Bibliotecas Compartilhadas (`lib/`)

- `Lib-OrchestratorRuntime.psm1`: Fonte única para scripts de `Infrastructure/`. Expõe:
  - `Get-OrchestratorRuntimeVersion`: Lê `ORCHESTRATOR_VERSION` de `constants.py`.
  - `Get-OrchestratorEnvValue`: Parser de variáveis do `.env`.
  - `Stop-OrchestratorProcesses`: Encerra processos com segurança utilizando `Get-CimInstance Win32_Process`.
  - **Atenção**: Nunca utilize `Get-Process` para filtrar processos por linha de comando no Windows PowerShell 5.1 (a propriedade `CommandLine` não é exposta).
- `Lib-Config.psm1`: Leitura segura de variáveis de ambiente para automações de domínio.

## Testes Unitários com Pester (5.7.1)

- A suíte de testes em `lib/tests` é um gate bloqueante de CI sempre que arquivos `.ps1`, `.psm1` ou `.js` forem alterados.
- Execução padrão:
  ```powershell
  Import-Module Pester -RequiredVersion 5.7.1 -Force
  Invoke-Pester -Path .\lib\tests -CI
  ```
- Teste pontual de arquivo:
  ```powershell
  Invoke-Pester -Path .\lib\tests\Lib-Config.Tests.ps1
  ```
