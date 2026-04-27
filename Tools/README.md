# Ecossistema de Manutencao e Governanca (`Tools/`)

Este diretorio concentra as ferramentas de suporte critico para a sustentacao e auditoria do hub de automacoes. Os utilitarios sao organizados por dominio de responsabilidade: **Governanca de Codigo**, **Sincronizacao VBA**, **Auditoria de Drift** e **Operacao de Scaffolding**.

---

## 🛡️ Governanca de Codigo e CI Local

Scripts automatizados vinculados ao **Hook de Pre-Commit** do Git, que bloqueiam o envio de codigo que nao siga o Padrao Ouro:

- **`ValidarAutomacoes.ps1`**: Orquestrador de auditoria. Exige que cada modulo possua seu `CONTEXT.md` e cabecalhos de Skill JSON.
- **`Test-LogConformidade.ps1`**: Enforce o formato BR (`dd/MM/yyyy`) e bloqueia a poluicao de logs diarios.
- **`Test-VbaPtBrGovernance.ps1`**: Garante a conformidade ASCII do VBE e limpa caracteres corrompidos.
- **`Test-PowerShellApprovedVerbs.ps1`**: Forca a padronizacao de nomenclatura PowerShell no formato `Verbo-Substantivo`.
- **`Test-SkillsGovernance.ps1`**: Valida a integridade tecnica das Skills (documentacao de IA).
- **`Invoke-VbaCompilationCheck.ps1`**: Parte do **Preflight**; detecta erros de sintaxe VBA antes do deploy.

---

## 🏗️ Sincronizacao e Versionamento VBA

Mecanicas para traducao entre o binario Excel (`.xlsm`) e o codigo versionavel (`.bas/.cls`):

- **`ExportarVbaModulos.ps1`**: Extrai o cerebro das planilhas para revisao no Git.
- **`SincronizarProjetoVba.ps1`**: Injecao deterministica de codigo do Git para o Excel.
- **`Sync-SharedVba.ps1`**: Sincroniza classes core (`_Shared/VBA`) entre todos os modulos ativos.

---

## 🔍 Auditoria de Drift e Metadados

- **`Test-VbaDrift.ps1`**: O "Cao de Guarda" do Git. Detecta se alguem alterou o Excel manualmente sem exportar o codigo para o repositorio.
- **`ExportarAuditoriaXlsm.ps1`**: Gera manifestos estruturais para comparacao de versoes binarias.

---

## ⚙️ Operacao e Higienizacao

- **`New-Automation.ps1`**: Gerador de scaffold para novas automacoes seguindo as regras nativas.
- **`AplicarPoliticaRetencao.ps1`**: Automacao de limpeza executada pelo Monitor (expurgo de lixo temporario e rotacao de logs).

---

## 🐍 Qualidade Python

O repositorio impoe o uso de:
- **Black Formatter**: Formatacao PEP8 absoluta.
- **isort**: Ordenacao de imports.
- **ASCII-Safe Logic**: Scripts Python devem ser mantidos sem caracteres acentuados crus no fonte, utilizando Escape Sequences se necessario.

---

## 🚀 Como Executar

A bateria completa de testes pode ser disparada manualmente para validar o repositorio:

```powershell
# Validacao completa de conformidade
.\Tools\ValidarAutomacoes.ps1
```

*Qualquer falha aqui impedira o 'git commit', garantindo que o Hub nunca regrida.*
