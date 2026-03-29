# Automação - Receitas Bloqueadas

## Visão Geral

Este projeto automatiza o processamento e a distribuição da planilha de **Receitas Bloqueadas**. A automação envolve a atualização de dados via Excel/VBA, envio de e-mails e distribuição do arquivo atualizado através do WhatsApp.

## Fluxo do Processo

O fluxo técnico completo segue esta ordem:

`MonitorAutomacoes.ps1` (Trigger) -> `RunMacro.vbs` -> `Receitas Bloqueadas.xlsm` (VBA) -> `RunWhatsApp.bat` -> `sendWhatsApp.js` (Node.js) -> **WhatsApp**

---

## Componentes do Projeto

### 1. Runner VBScript (`RunMacro.vbs`)
Responsável por orquestrar o início do processo:
- Inicia a instância do Excel em modo invisível.
- Abre o arquivo `Receitas Bloqueadas.xlsm`.
- Executa a macro principal `ExecutarProcessoCompleto`.
- Gera um `ExecId` único (baseado em timestamp) para rastreabilidade.
- Dispara o `RunWhatsApp.bat` de forma síncrona e oculta.
- Log principal: `C:\Automacoes\Receitas Bloqueadas\ReceitasBloqueadas.txt`.

### 2. Workbook Excel (`Receitas Bloqueadas.xlsm`)
Contém a inteligência de negócio no VBA:
- Atualiza as conexões de dados (Power Query/Connections).
- Ajusta a formatação de data para o padrão PT-BR (`dd/mm/yyyy`).
- Gera o corpo do e-mail em HTML.
- Realiza o envio do e-mail (se houver dados na tabela).
- Salva o arquivo final para ser enviado pelo WhatsApp.

### 3. Launcher Batch (`RunWhatsApp.bat`)
Atua como um validador de ambiente e bootstrap para o Node.js:
- Valida a existência dos pré-requisitos (Node.exe, Script, Config).
- Gerencia o modo de execução (AUTO vs PAIRING).
- Se a sessão do WhatsApp estiver expirada ou ausente, lança automaticamente uma janela CMD visível para o pareamento do QR Code.
- Captura e loga o `ERRORLEVEL` do Node.js.
- Aplica lock local de execução (`.sendwhatsapp.lock`) para evitar concorrência entre duas instâncias silenciosas.

### 4. Distribuidor Node.js (`sendWhatsApp.js`)
Utiliza a biblioteca `whatsapp-web.js` para o envio das mensagens:
- Carrega as configurações de `whatsapp-config.json`.
- **Validação e Resolução**: Identifica se o destino é um grupo ou contato e resolve o ID interno do WhatsApp.
- **Idempotência**: Verifica no `whatsapp-state.json` se esta execução específica já foi enviada, evitando duplicidade.
- **Envio Dinâmico**: Pode enviar apenas texto ou arquivo anexo com legenda personalizável.
- **Retry**: Sistema de tentativas automáticas em caso de falhas temporárias de conexão.

---

## Configuração (`whatsapp-config.json`)

O comportamento do envio via WhatsApp é totalmente parametrizável:

- **target**: Define o tipo do destino (`group` ou `contact`), o nome do grupo ou telefone do contato, e a lista de menções (`@`).
- **message**: Controla se o anexo deve ser enviado e o conteúdo da legenda (Título, Corpo, ExecId).
- **runtime**: `headless: true` para execução em segundo plano ou `false` para depuração visual.
- **retry**: Configurações de tempo e tentativas para garantir a entrega.
- **paths**: Define os caminhos dos arquivos de log, estado e autenticação.
- **idempotency**:
  - `enabled`: ativa prevenção de reenvio por execução.
  - `retryFailedAfterMs`: define cooldown para tentar novamente a mesma entrega após falha.
  - `keepSuccessForMs` e `keepFailureForMs`: definem retenção de histórico no `whatsapp-state.json`.

---

## Operação e Manutenção

### Modos de Execução
- **Modo AUTO (Normal)**: Executado pelo monitor agendado. Roda de forma oculta e silenciosa.
- **Modo PAIRING**: Invocado manualmente ou via `RunWhatsApp.bat` quando é necessário escanear o QR Code. Abre uma janela de terminal visível.

### Logs e Diagnóstico
- **Log Consolidado**: `C:\Automacoes\Receitas Bloqueadas\ReceitasBloqueadas.txt`
  - Contém a trilha completa com prefixos `[VBS]`, `[BAT]` e `[NODE]`.
- **Log de Bootstrap**: `sendWhatsApp-bootstrap.log`
  - Utilizado para diagnosticar problemas graves no início da execução do Node.js.

### Códigos de Erro Comuns (Exportados pelo Node)
- `11`: Anexo não encontrado no caminho configurado.
- `20`: Falha final após esgotar tentativas de envio.
- `21`: Reautenticação necessária (Sessão expirada).
- `22`: Erro de validação no arquivo de configuração (`whatsapp-config.json`).
- `23`: Cooldown de retry ativo para a mesma entrega (envio adiado sem nova tentativa).
- `0`: Sucesso ou recurso desabilitado por configuração.

### Códigos Operacionais do BAT
- `40`: Execução concorrente detectada (lock ativo). Nesse caso o envio é ignorado para evitar corrida de sessão.

---

## Regras de Negócio Críticas
1. **Ordem de Precedência**: O envio do WhatsApp é a última etapa e só ocorre após o salvamento bem-sucedido da planilha pelo VBA.
2. **Segurança de Dados**: O e-mail e o WhatsApp só são disparados se a planilha processada contiver dados válidos.
3. **Persistência de Sessão**: A autenticação do WhatsApp é mantida na pasta `.wwebjs_auth` para evitar pareamentos repetitivos.
4. **Proteção contra concorrência**: Apenas uma execução silenciosa do bridge pode ficar ativa por vez.
