# Fixtures Operacionais do Worker

Este diretório contém entrypoints mínimos usados para validar comportamento do worker e do dashboard sem acionar canais reais.

## Arquivos

- `run.ps1`, `run0.ps1`, `run1.ps1`, `run2.ps1`, `run3.ps1`, `run4.ps1`
  - Smoke scripts simples para testes rápidos de execução.
- `run_validation_log_stream_exit24.ps1`
  - Fixture segura para validar:
    - streaming online de logs no modal de execução do dashboard;
    - persistência progressiva de `stdout` no runtime;
    - classificação final de `exit_code=24` como falha de canal.

## Regra de uso

- Este script não deve chamar WhatsApp, e-mail, Oracle ou qualquer integração externa.
- O uso esperado é cadastrar temporariamente uma automação apontando para o script, executar a validação do fluxo e remover o cadastro ao final.
