# Ferramentas de Manutenção e Governança (`Tools/`)

Este diretório contém os utilitários de suporte para o ecossistema de automações. As ferramentas são divididas em categorias: **Governança**, **Sincronização VBA**, **Auditoria** e **Operação**.

## 🛡️ Governança e CI Local

Estes scripts são invocados automaticamente pelos hooks de pre-commit ou pelo validador central:

- **`Test-VbaPtBrGovernance.ps1`**: Valida se arquivos `.bas/.cls` seguem o padrão ASCII e alerta sobre termos em PT-BR sem acentuação.
- **`Test-PowerShellApprovedVerbs.ps1`**: Garante que scripts PowerShell usem verbos aprovados (`Get-`, `New-`, `Invoke-`).
- **`Test-SkillsGovernance.ps1`**: Valida a conformidade técnica dos arquivos de Skill do Gemini CLI.
- **`Test-LogConformidade.ps1`**: Rejeita formatos de log obsoletos (Data ISO, Logs diários).
- **`Test-DashboardTemplate.ps1`**: Valida o contrato técnico do template HTML do dashboard.
- **`Test-VbaComponentTypes.ps1`**: Valida se componentes VBA foram importados com o tipo correto (Classe vs Módulo).
- **`Test-VbaReferences.ps1`**: Verifica se existem referências quebradas (Missing References) nos projetos VBA.
- **`Invoke-VbaCompilationCheck.ps1`**: Tenta compilar os projetos VBA para detectar erros de sintaxe ou referências.
- **`ValidarAutomacoes.ps1`**: Orquestrador que executa todos os testes de governança acima em sequência.

---

## 🏗️ Sincronização de Código VBA

Utilitários para converter o código entre o repositório (texto) e os workbooks (binário):

- **`ExportarVbaModulos.ps1`**: Extrai módulos do `.xlsm` para arquivos `.bas/.cls` no repositório.
- **`SincronizarProjetoVba.ps1`**: Importa os arquivos `.bas/.cls` do repositório para dentro do `.xlsm`.
- **`ImportarClassesVba.ps1`**: Importa apenas as classes compartilhadas (`_Shared/VBA`) para um projeto.
- **`SyncVbaModulos.ps1`**: Wrapper simplificado para sincronização bidirecional.

---

## 🔍 Auditoria e Drift

Para detectar alterações não rastreadas e metadados de workbooks:

- **`ExportarAuditoriaXlsm.ps1`**: Gera manifestos JSON com metadados dos workbooks (tamanho, componentes).
- **`Test-VbaDrift.ps1`**: Compara o código atual com os snapshots em `Audit/` para detectar alterações manuais no Excel que não foram commitadas.
- **`CompararVbaModulos.ps1`**: Gera relatórios detalhados de diferenças entre fontes VBA.

---

## ⚙️ Operação e Scaffolding

- **`New-Automation.ps1`**: Cria a estrutura de diretórios, runner e configuração para uma nova automação.
- **`AplicarPoliticaRetencao.ps1`**: Remove logs e artefatos de auditoria antigos (executado pelo monitor diariamente às 02:20).
- **`ValidarVbaAntesImportar.ps1`**: Realiza checagem de integridade nos arquivos `.bas/.cls` antes da importação.

---

## 🚀 Como Executar

A maioria das ferramentas pode ser invocada via PowerShell (pwsh):

```powershell
# Exemplo: Validar governança completa localmente
pwsh -File .\Tools\ValidarAutomacoes.ps1 -OnlyGovernance
```

Consulte o cabeçalho de cada script para ver a lista completa de parâmetros e exemplos.
