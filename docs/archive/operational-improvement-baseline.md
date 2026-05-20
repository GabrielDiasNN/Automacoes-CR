# Baseline de Melhoria Operacional

Data: 2026-05-18

## Fotografia inicial

- Branch local: `main` à frente de `origin/main` por 2 commits.
- Worktree inicial: mudanças pendentes em `.gitignore`, `CHANGELOG.md`, documentação de `Receitas Bloqueadas` e `lib/WhatsApp-Core.js`; esses arquivos foram preservados como trabalho pré-existente.
- Governança agregada: aprovada antes da implementação com Zero Trust, SQL, Python, PowerShell, portabilidade, encoding, JSON, skills e Dashboard template.
- Testes críticos do Orchestrator: aprovados antes da implementação com 42 cenários.
- Pendência ambiental: cache do pytest sem permissão de escrita em `Orchestrator/.pytest_cache`; mitigado com `Orchestrator/pytest.ini` desabilitando o cache de teste.

## Mudança operacional implementada

- `/api/system/diagnostics` agora expõe achados com impacto, prioridade e ação estruturada.
- O payload de diagnóstico inclui ações consolidadas para o operador, hotspots de falhas nas últimas 24h e fila ativa por prioridade/grupo.
- A tela `Sistema` renderiza atalhos acionáveis a partir do diagnóstico.
- A tela `Execuções` exibe motivo de falha, ação de recuperação, contagem de retry e botão de requeue quando o contrato permitir.

## Evidência esperada por entrega

- Snapshot de Git antes de mutações.
- Testes focados do contrato alterado.
- Suíte crítica do Orchestrator.
- Governança e encoding.
- Playwright E2E por último quando houver alteração de Dashboard/UI ou contrato front-back.
