# Plano de Migração: VBS Triggers → PS-nativo (`run.ps1`)

> **Versão:** 2.0
> **Data:** Abril 2026
> **Status:** Cutover RE + RB executado — aguardando validação em produção
> **Pré-requisito:** Estabilização concluída — VBA classes corrigidas (ClassModule), VBS triggers ExitCode=0 para todas as 3 automações.

---

## 1. Visão Geral

### O que muda

| Componente          | ANTES (VBS)                                                 | DEPOIS (PS)                              |
| ------------------- | ----------------------------------------------------------- | ---------------------------------------- |
| **Trigger**         | `Trigger_Automation.vbs` via `wscript.exe`                  | `run.ps1` via `powershell.exe`           |
| **WhatsApp (RB)**   | `RunWhatsApp.bat` (171 linhas, lógica embarcada)            | `Send-WhatsApp.ps1` (lib unificada)      |
| **Logging**         | Inline no VBS                                               | `Lib-Logging.psm1` (módulo centralizado) |
| **Compatibilidade** | Exit codes idênticos (0-7, 23, 40) — sem mudança no Monitor |

### Ordem de migração

```
RE (Receitas Emitidas) → RB (Receitas Bloqueadas) → Montagem (futuro, fora de escopo)
```

**Justificativa:** RE é a mais simples (sem WhatsApp, roda 1x/semana sexta 07:05). RB envolve WhatsApp (componente não testado em produção). Montagem não tem `run.ps1` criado.

---

## 2. Pré-requisitos (verificar antes de iniciar)

- [x] **VBA ClassModule OK**: `clsAppContext`, wrappers RB/RE todos Type=2 (já corrigido)
- [x] **VBS ExitCode=0**: Todas as 3 automações funcionando via VBS (já validado)
- [x] **`lib/` existente**: `Lib-Logging.psm1`, `Lib-Email.psm1`, `Send-WhatsApp.ps1` presentes
- [x] **Node.js instalado**: `node.exe` em `C:\Program Files\nodejs\` (necessário para WhatsApp)
- [ ] **Sessão WhatsApp ativa**: `.wwebjs_auth/session-receitas-bloqueadas/` presente (para RB)
- [ ] **Nenhum Excel aberto**: `Get-Process excel` deve retornar vazio
- [x] **Monitor parado**: Parar o Monitor antes de alterar `config.json` (evitar reload com config parcial)

---

## 3. Etapa 1 — Receitas Emitidas (piloto)

### 3.1. Teste manual isolado

**Objetivo:** Validar `run.ps1` RE sem envolver o Monitor.

```powershell
# 1. Verificar que nenhum Excel está aberto
Get-Process excel -ErrorAction SilentlyContinue

# 2. Executar run.ps1 manualmente
pwsh -NoProfile -ExecutionPolicy Bypass -File "C:\Automacoes\Receitas Emitidas\run.ps1" "TESTE_MANUAL_001"

# 3. Verificar exit code
echo "ExitCode: $LASTEXITCODE"

# 4. Conferir log
Get-Content "C:\Automacoes\Receitas Emitidas\Logs\Execution.log" -Tail 30
```

**Critérios de aprovação:**

- ExitCode = 0
- Log mostra `INICIO`, execução da macro `AtualizarEEnviarOutlook`, monitoramento VBA, `FIM - Finalizado. ExitCode=0`
- Workbook processou corretamente (conferir resultado na planilha se aplicável)
- Nenhum processo Excel zumbi após conclusão

**Rollback:** Nenhuma alteração no config.json neste passo. Se falhar, basta diagnosticar o `run.ps1`.

### 3.2. Cutover para Monitor

**Somente após teste manual ExitCode=0.**

```powershell
# 1. PARAR o Monitor (fechar a janela ou Ctrl+C se terminal)

# 2. Alterar config.json
# DE:
#   "scriptPath": "C:\\Automacoes\\Receitas Emitidas\\Trigger_Automation.vbs"
# PARA:
#   "scriptPath": "C:\\Automacoes\\Receitas Emitidas\\run.ps1"

# 3. Reiniciar o Monitor
```

**Alteração no `config.json`:**

```json
{
  "name": "Receitas Emitidas",
  "scriptPath": "C:\\Automacoes\\Receitas Emitidas\\run.ps1",
  ...
}
```

O Monitor já suporta `.ps1` nativamente em `Start-TaskProcess` (linha 822 do `MonitorAutomacoes.ps1`):

```powershell
elseif ($ext -eq ".ps1") {
    $proc = Start-Process "powershell.exe" -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$Path`" `"$execId`"" ...
}
```

### 3.3. Validação pós-cutover

**Critério:** RE roda somente **sextas-feira às 07:05**. Aguardar **2 execuções bem-sucedidas consecutivas** (2 sextas) antes de prosseguir.

- [ ] Sexta 1: ExitCode=0 no log do Monitor
- [ ] Sexta 2: ExitCode=0 no log do Monitor

**Verificação:**

```powershell
# Conferir logs do Monitor
Get-Content "C:\Automacoes\Logs\Monitor_*.log" -Tail 50 | Select-String "Receitas Emitidas"

# Conferir log interno do run.ps1
Get-Content "C:\Automacoes\Receitas Emitidas\Logs\Execution.log" -Tail 30
```

### 3.4. Rollback RE

Se qualquer execução falhar:

```powershell
# 1. PARAR o Monitor

# 2. Reverter config.json para VBS
# DE:   "scriptPath": "C:\\Automacoes\\Receitas Emitidas\\run.ps1"
# PARA: "scriptPath": "C:\\Automacoes\\Receitas Emitidas\\Trigger_Automation.vbs"

# 3. Reiniciar o Monitor
```

Tempo de rollback: < 1 minuto. Nenhum outro arquivo é alterado.

---

## 4. Etapa 2 — Receitas Bloqueadas

### 4.1. Teste do Send-WhatsApp.ps1 (isolado)

**Pré-requisito:** Testar o bridge WhatsApp antes de tocar no `run.ps1`.

```powershell
# Verificar pré-requisitos
Test-Path "C:\Program Files\nodejs\node.exe"
Test-Path "C:\Automacoes\Receitas Bloqueadas\sendWhatsApp.js"
Test-Path "C:\Automacoes\Receitas Bloqueadas\whatsapp-config.json"
Test-Path "C:\Automacoes\Receitas Bloqueadas\.wwebjs_auth\session-receitas-bloqueadas"

# Teste seco (se sendWhatsApp.js suporta dry-run / apenas validação de sessão)
# Caso contrário, validar que sessão LocalAuth existe:
Get-ChildItem "C:\Automacoes\Receitas Bloqueadas\.wwebjs_auth\session-receitas-bloqueadas" | Select-Object Name, Length
```

> **ATENÇÃO:** `Send-WhatsApp.ps1` em modo `AUTO` **envia mensagem real** se sessão ativa. Testar somente quando houver dados reais para enviar (pós-execução da macro VBA) ou em modo `PAIRING` para validar sessão.

### 4.2. Teste manual do run.ps1 RB

```powershell
# 1. Garantir Excel fechado
Get-Process excel -ErrorAction SilentlyContinue

# 2. Executar
pwsh -NoProfile -ExecutionPolicy Bypass -File "C:\Automacoes\Receitas Bloqueadas\run.ps1" "TESTE_MANUAL_RB_001"

# 3. Verificar
echo "ExitCode: $LASTEXITCODE"

# 4. Logs
Get-Content "C:\Automacoes\Receitas Bloqueadas\ReceitasBloqueadas.txt" -Tail 40
```

**Critérios de aprovação:**

- ExitCode = 0 (ou 23/40 se WhatsApp em cooldown/lock — aceitável)
- Macro `ExecutarProcessoCompleto` executou
- Log VBA mostra `FIM DO PROCESSO. Resultado=Sucesso`
- WhatsApp enviado (ou aviso claro no log se sessão ausente)
- Nenhum Excel zumbi

### 4.3. Cutover RB para Monitor

```powershell
# 1. PARAR o Monitor

# 2. Alterar config.json:
# DE:   "scriptPath": "C:\\Automacoes\\Receitas Bloqueadas\\Trigger_Automation.vbs"
# PARA: "scriptPath": "C:\\Automacoes\\Receitas Bloqueadas\\run.ps1"

# 3. Reiniciar o Monitor
```

### 4.4. Validação pós-cutover

**RB roda seg-sex às 07:30 e 15:30.** Critério: **3 execuções consecutivas ExitCode=0** (1,5 dias úteis).

- [ ] Execução 1: ExitCode=0
- [ ] Execução 2: ExitCode=0
- [ ] Execução 3: ExitCode=0

```powershell
Get-Content "C:\Automacoes\Logs\Monitor_*.log" -Tail 80 | Select-String "Receitas Bloqueadas"
Get-Content "C:\Automacoes\Receitas Bloqueadas\ReceitasBloqueadas.txt" -Tail 40
```

### 4.5. Rollback RB

```powershell
# 1. PARAR o Monitor

# 2. Reverter config.json
# DE:   "scriptPath": "C:\\Automacoes\\Receitas Bloqueadas\\run.ps1"
# PARA: "scriptPath": "C:\\Automacoes\\Receitas Bloqueadas\\Trigger_Automation.vbs"

# 3. Reiniciar o Monitor
```

### 4.6. Migração do RunWhatsApp.bat (pós-validação)

**Somente após RB run.ps1 validado em produção (3+ execuções OK).**

O `RunWhatsApp.bat` atual (171 linhas) é o fallback do VBS trigger. Com `run.ps1` + `Send-WhatsApp.ps1` em produção, o BAT pode ser substituído por um shim que redireciona para o PS:

```bat
@echo off
REM Shim — redireciona para Send-WhatsApp.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Automacoes\lib\Send-WhatsApp.ps1" -ExecId "%~1" -Mode "%~2"
exit /b %ERRORLEVEL%
```

> **IMPORTANTE:** Somente substituir o BAT quando não houver mais necessidade de rollback para VBS (VBS chama `RunWhatsApp.bat` diretamente).

---

## 5. Etapa 3 — Montagem de Terceirizados (futuro)

> **Fora de escopo desta migração.** Montagem não possui `run.ps1` criado.

Quando for implementar:

1. Criar `Montagem de Terceirizados/run.ps1` seguindo o padrão de RB/RE
2. Macro: `ExecutarValidacao` (verificar nome exato no VBA)
3. Log VBA: dinâmico por data (padrão `log_DD-MM-YYYY.log`)
4. Sem WhatsApp
5. Testar manualmente → cutover → validar 5+ execuções (roda a cada hora cheia seg-sex)

---

## 6. Diferenças técnicas VBS vs PS

| Aspecto            | VBS (`Trigger_Automation.vbs`)           | PS (`run.ps1`)                                         |
| ------------------ | ---------------------------------------- | ------------------------------------------------------ |
| **COM Automation** | `CreateObject("Excel.Application")`      | `New-Object -ComObject Excel.Application`              |
| **Log VBA RE**     | `VBA_Internal.log` (estático)            | `VBA_Internal.log` (estático) — ✅ idêntico            |
| **Log VBA RB**     | `log_DD-MM-YYYY.log` (dinâmico)          | `log_DD-MM-YYYY.log` (dinâmico) — ✅ idêntico          |
| **WhatsApp (RB)**  | `RunWhatsApp.bat` (embarcado)            | `Send-WhatsApp.ps1` (via Start-Process)                |
| **COM Cleanup**    | `Set obj = Nothing`                      | `ReleaseComObject()` + `.Quit()` — ✅ mais robusto     |
| **Timeout**        | 300s (ambos)                             | 300s (ambos) — ✅ idêntico                             |
| **Exit codes**     | 0-8, 23, 40                              | 0-7, 23, 40 — ✅ compatível                            |
| **ExecId**         | Passado pelo Monitor como arg posicional | Passado pelo Monitor como arg posicional — ✅ idêntico |
| **ReadOnly check** | `wb.ReadOnly` → ExitCode 7               | `$wb.ReadOnly` → ExitCode 7 — ✅ idêntico              |

### Log paths (diferença a observar)

| Automação | VBS log path             | PS log path              | Observação                       |
| --------- | ------------------------ | ------------------------ | -------------------------------- |
| **RB**    | `ReceitasBloqueadas.txt` | `ReceitasBloqueadas.txt` | ✅ Idêntico                      |
| **RE**    | Log via echo/VBS interno | `Logs/Execution.log`     | ⚠ PS grava em arquivo (melhoria) |

---

## 7. Checklist de validação final

### Pós-migração RE + RB

- [x] `config.json` aponta para `run.ps1` em RE e RB
- [x] Monitor recarregou config (verificar hash no log)
- [ ] RE: 2+ execuções sexta ExitCode=0
- [ ] RB: 3+ execuções seg-sex ExitCode=0
- [ ] WhatsApp entregue em pelo menos 1 execução RB
- [ ] Nenhum processo Excel zumbi (`Get-Process excel` vazio entre execuções)
- [ ] `Test-VbaDrift.ps1` retorna `[OK] VBA sincronizado`
- [ ] Logs estruturados com ExecId em todos os registros

### Commit final

Após validação completa:

```powershell
git add config.json
git commit -m "feat(config): migrar RE e RB de VBS triggers para run.ps1 PS-nativo

- Receitas Emitidas: scriptPath → run.ps1 (validado 2 sextas consecutivas)
- Receitas Bloqueadas: scriptPath → run.ps1 (validado 3+ execuções)
- WhatsApp migrado de RunWhatsApp.bat para Send-WhatsApp.ps1
- Exit codes compatíveis, sem impacto no MonitorAutomacoes.ps1"
```

---

## 8. Riscos e mitigações

| Risco                              | Probabilidade | Impacto | Mitigação                                                                                     |
| ---------------------------------- | ------------- | ------- | --------------------------------------------------------------------------------------------- |
| `run.ps1` falha no COM Excel       | Baixa         | Alto    | Teste manual antes do cutover; rollback em < 1min                                             |
| WhatsApp sessão expirada           | Média         | Médio   | `Send-WhatsApp.ps1` auto-redireciona para PAIRING (exit 21)                                   |
| Excel zumbi (processo não encerra) | Baixa         | Alto    | `ReleaseComObject` + `Quit()` no finally; Monitor tem `maxRuntimeMinutes`                     |
| `Lib-Logging.psm1` ausente         | Muito baixa   | Baixo   | Fallback inline na função `_Log` (já implementado)                                            |
| Git CRLF → LF em `.cls`            | Baixa         | Alto    | Já mitigado: `Test-VbaDrift.ps1` usa hash byte-level; importação via `ImportarClassesVba.ps1` |
| Node.js crash no WhatsApp          | Baixa         | Médio   | Lock + cleanup automático em `Send-WhatsApp.ps1`; exit code pass-through                      |

---

## 9. Sequência resumida

```
┌─────────────────────────────────────────────────┐
│  1. Teste manual RE run.ps1     → ExitCode=0?   │
│     SIM → Cutover RE config.json                 │
│     NÃO → Diagnosticar, não prosseguir           │
├─────────────────────────────────────────────────┤
│  2. Validar 2 sextas RE         → 2x ExitCode=0? │
│     SIM → Prosseguir para RB                     │
│     NÃO → Rollback RE → VBS                      │
├─────────────────────────────────────────────────┤
│  3. Teste Send-WhatsApp.ps1     → Sessão ativa?  │
│     SIM → Teste manual RB run.ps1                │
│     NÃO → PAIRING primeiro                       │
├─────────────────────────────────────────────────┤
│  4. Teste manual RB run.ps1     → ExitCode=0?    │
│     SIM → Cutover RB config.json                 │
│     NÃO → Diagnosticar, não prosseguir           │
├─────────────────────────────────────────────────┤
│  5. Validar 3 exec RB           → 3x ExitCode=0? │
│     SIM → Migração concluída ✅                  │
│     NÃO → Rollback RB → VBS                      │
├─────────────────────────────────────────────────┤
│  6. (Opcional) Shim RunWhatsApp.bat               │
│  7. (Futuro) Montagem run.ps1                     │
└─────────────────────────────────────────────────┘
```
