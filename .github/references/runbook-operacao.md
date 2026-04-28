# Runbook de Operação — Automacoes Hub (v2.0)

:: { "version": "2.0.0", "skill": "ai-native-development-standard", "description": "Guia Enterprise para Diagnóstico e Resolução de Incidentes." }

## Objetivo
Manual técnico para resposta a incidentes, focado em resiliência, segurança e sustentabilidade por IA.

---

## 🚨 Dicionário de Exit Codes (Contrato de Execução)

| Código | Categoria | Significado | Ação Sugerida |
| --- | --- | --- | --- |
| **0** | Sucesso | Execução concluída sem alertas. | Nenhuma. |
| **1** | Fatal | Erro inesperado no código ou crash. | Verificar log via `ExecId`. |
| **4** | VBA/Macro | Falha ao chamar ou executar macro Excel. | Abrir XLSM e compilar (VBE). |
| **6** | Business | Conclusão anormal (Regra de negócio violada). | Revisar dados de entrada. |
| **7** | Lock | Workbook em somente leitura ou travado. | Limpar processos Excel órfãos. |
| **9** | **Pre-Flight** | **Ambiente instável (Disco, Rede ou Paths).** | **Verificar saúde da infraestrutura.** |
| **21** | Auth | Sessão WhatsApp expirada. | Executar modo PAIRING. |
| **23** | Cooldown | WhatsApp em período de descanso. | Aguardar e não forçar execução. |
| **40** | Concorrência | Outra instância da tarefa está ativa. | Aguardar término da anterior. |

---

## 🔍 Protocolo de Diagnóstico AI-Native

### 1. Falha no Pre-Flight (Exit Code 9)
**Sintoma:** O robô nem inicia a lógica de negócio.
1.  Localize a linha `[PS] [ERRO] [ExecId:...] Pre-Flight:...`
2.  Verifique se o servidor Oracle `SRVDB02` responde ao ping.
3.  Verifique se há menos de 1GB de espaço no disco `C:`.
4.  Confirme se a pasta `Legacy/` ou o `.venv` foram movidos acidentalmente.

### 2. Mojibake ou Caracteres Quebrados
**Sintoma:** Logs ilegíveis no console ou arquivo.
1.  Confirme se o script está usando o **Base64 Bridge Protocol**.
2.  Logs prefixados com `B64:` devem ser lidos preferencialmente via VS Code (que decodifica via extensões) ou através da ferramenta `Tools\Open-LatestLog.ps1`.

### 3. Dados Mascarados ([REDACTED])
**Sintoma:** Log exibe `g***@domain.com` ou `[REDACTED]`.
1.  Isso é o **Auto-Masking** da `Lib-Logging` em ação.
2.  Se precisar do dado real para depuração, consulte a base de dados original (Oracle) ou a variável de ambiente, **nunca tente desabilitar o masking em produção**.

### 4. Falha na Ponte Híbrida (Excel -> Python)
**Sintoma:** O Excel faz o refresh, mas o Python não lê os dados.
1.  Verifique se o processo `Excel.exe` foi encerrado corretamente.
2.  Confirme se a tabela no Excel não mudou de nome (`VW_EXC_OB_PED_ROM_Faccao`).
3.  Verifique se a biblioteca `openpyxl` está instalada no `.venv`.

---

## 🛠️ Ordem Padrão de Resposta
1.  **Isolamento:** Identifique o `ExecId` único da falha.
2.  **Contexto:** Leia o arquivo `CONTEXT.md` da automação afetada.
3.  **Saúde e Governança:** Execute `Tools\ValidarAutomacoes.ps1` e os novos scanners de governança (`Test-PythonGovernance.ps1`, `Test-ZeroTrust.ps1`, `Test-PowerShellGovernance.ps1`) para descartar falhas de estrutura, tipagem ou senhas vazadas que bloquearam a CI.
4.  **Simulação:** Execute o script com a flag `-EmailPreviewOnly` ou em modo manual para ver o erro em tempo real.
5.  **Rollback:** Se a alteração for recente, reverta para o commit anterior estável.

---

## 📝 Registro de Incidente para a IA
Ao pedir ajuda a uma IA para resolver um problema, forneça:
1.  O `ExecId` da falha.
2.  O trecho do log contendo o erro.
3.  O `CONTEXT.md` da pasta.
4.  O resultado do Pre-Flight Check.
