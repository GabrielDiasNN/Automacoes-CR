# Runbook Operacional: Receitas Emitidas

[⬅️ Voltar para o Hub Central](../../README.md)

## Ficha Técnica

- Componente: `Receitas Emitidas`
- Criticidade: `MÉDIA`
- SLA de recuperação: `6 horas`
- Horário de disparo: `Seg-Sex às 17:00`
- Área de negócio: `Planejamento / Tinturaria / PCP`
- Entrypoint operacional: `Receitas Emitidas/run.ps1`

## Objetivo

Gerar e distribuir o relatório de receitas emitidas para apoiar o planejamento da cozinha de químicos e a sequência de tingimento.

## Dependências

- Oracle para extração via `extract_oracle.py`
- Python para geração do HTML adaptativo
- Outlook COM para distribuição do e-mail

## Procedimento de Triagem

1. Validar no dashboard se a automação ficou sem sucesso recente ou com atraso operacional.
2. Conferir `Receitas Emitidas/Logs/` para separar falha de extração Oracle, geração do HTML ou envio por Outlook.
3. Quando houver `Exit Code 2`, tratar como idempotência e não como falha operacional.
4. Reexecutar apenas se o último estado não tiver sido consolidado com sucesso.

## Ação Manual de Contingência

1. Entrar em `Receitas Emitidas/`.
2. Executar `run.ps1`.
3. Confirmar a geração do payload extraído, do HTML final e o envio do e-mail.

## Sinais de Atenção

- Timeouts ou instabilidade do Oracle.
- Drift de encoding entre PowerShell e Python no pipeline StdIO.
- Falha de Outlook COM após geração correta do relatório.
