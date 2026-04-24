# Ecossistema de Manutenção e Governança (`Tools/`)

Este diretório concentra as ferramentas de suporte crítico para a sustentação e auditoria do hub de automações. Os utilitários são organizados por domínio de responsabilidade: **Governança de Código**, **Sincronização VBA**, **Auditoria de Drift** e **Operação de Scaffolding**.

---

## 🛡️ Governança de Código e CI Local

Scripts automatizados (invocados pelo `ValidarAutomacoes.ps1` ou hooks de Git) que asseguram a qualidade técnica do repositório:

- **`Test-VbaPtBrGovernance.ps1`**: Garante a conformidade ASCII do VBE e audita termos em PT-BR para visibilidade do usuário.
- **`Test-PowerShellApprovedVerbs.ps1`**: Força a padronização de nomenclatura PowerShell no formato `Verbo-Substantivo` (Singular).
- **`Test-SkillsGovernance.ps1`**: Valida a estrutura técnica e discovery das skills do Gemini CLI.
- **`Test-LogConformidade.ps1`**: Rejeita formatos de log obsoletos ou data ISO em arquivos de saída.
- **`Test-DashboardTemplate.ps1`**: Valida placeholders e mitigação XSS no template HTML do dashboard.
- **`Test-VbaComponentType.ps1`**: Audita se a tipagem dos componentes VBA no disco corresponde à estrutura do workbook.
- **`Test-VbaReferenceCheck.ps1`**: Detecta referências faltantes (`Missing References`) nos projetos Excel.
- **`Invoke-VbaCompilationCheck.ps1`**: Componente de **Preflight** que valida a compilação do projeto antes da execução em produção.
- **`ValidarAutomacoes.ps1`**: Orquestrador central que executa a bateria completa de testes de integridade.

---

## 🐍 Qualidade de Código Python

Com a migração para a arquitetura nativa, o repositório utiliza ferramentas profissionais para garantir a qualidade do código Python:

- **Black Formatter**: Utilizado como formatador de código padrão (PEP8).
- **isort**: Automatiza a organização de imports.
- **Pylance**: Fornece análise estática e type-checking no VS Code.

As tarefas para automação dessas ferramentas estão disponíveis no VS Code (`Tasks: Run Task` -> `Python: ...`).

---

## 🏗️ Sincronização e Versionamento VBA

Mecânicas para tradução de código entre os formatos binário (`.xlsm`) e texto (`.bas/.cls`):

- **`ExportarVbaModulos.ps1`**: Extrai módulos do binário para versionamento e revisão no repositório.
- **`SincronizarProjetoVba.ps1`**: Implementa a injeção determinística de módulos de texto para dentro do workbook.
- **`ImportarClassesVba.ps1`**: Sincroniza exclusivamente as classes compartilhadas (`_Shared/VBA`) para garantir a consistência de bibliotecas base.
- **`SyncVbaModulos.ps1`**: Interface simplificada para sincronização bidirecional.

---

## 🔍 Auditoria de Drift e Metadados

Ferramentas para detecção de alterações não documentadas:

- **`ExportarAuditoriaXlsm.ps1`**: Consolida metadados estruturais dos workbooks em manifestos JSON (`Audit/xlsm/`).
- **`Test-VbaDrift.ps1`**: Compara o código de produção com os snapshots de auditoria para detectar alterações "fora do Git".
- **`CompararVbaModulos.ps1`**: Gera diferenciais técnicos (Diff) entre versões de módulos VBA.

---

## ⚙️ Scaffolding e Higienização Operacional

- **`New-Automation.ps1`**: Scaffold completo para novas automações (diretórios, runner, VBS e registro no `config.json`).
- **`AplicarPoliticaRetencao.ps1`**: Automação diária para limpeza de artefatos temporários e logs antigos (executado pelo Monitor às 02:20).
- **`ValidarVbaAntesImportar.ps1`**: Gate de segurança que valida a integridade de módulos de texto antes da injeção no Excel.

---

## 🚀 Protocolo de Execução

As ferramentas devem ser executadas preferencialmente via PowerShell Core (`pwsh`):

```powershell
# Execução da governança local estrita
pwsh -File .\Tools\ValidarAutomacoes.ps1 -OnlyGovernance -FailOnWarnings
```

*Consulte a documentação inline em cada script para especificações de parâmetros.*
