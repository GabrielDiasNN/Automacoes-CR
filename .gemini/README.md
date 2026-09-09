# Gemini Workspace Notes

## Skills

- `.gemini/skills/` e um espelho de compatibilidade para Gemini CLI e Antigravity.
- A fonte canonica continua sendo `.github/skills/`.
- Nao edite skills diretamente em `.gemini/skills/` se o item for um link para `.github/skills/`.

## Regra pratica

- Atualize sempre `.github/skills/`.
- Preserve os links em `.gemini/skills/` apontando para as mesmas 7 skills ativas.
- Se uma skill existir em `.github/skills/` e nao aparecer em `.gemini/skills/`, trate como problema de espelhamento do ambiente.

## Servidor MCP `sqlite-orchestrator`

Aponta para `Orchestrator/automacoes.db` — o banco **real** desta maquina, nao
uma copia.

> [!IMPORTANT]
> **A garantia de somente-leitura ainda nao foi verificada nesta maquina.**
> A flag `--read-only` esta declarada em `settings.json`, mas nao foi possivel
> confirmar que a versao instalada de `mcp-server-sqlite` a suporta (o acesso ao
> PyPI depende de proxy autenticado). Enquanto a verificacao nao for feita, ha
> dois desfechos possiveis: o servidor recusa o argumento e nao sobe, ou o
> ignora e expoe as ferramentas de escrita (`write_query`, `create_table`)
> contra o banco de producao.
>
> Antes de usar este servidor, rode `uvx mcp-server-sqlite --help` num ambiente
> com rede e confirme a flag. Se ela nao existir, nao mantenha esta
> configuracao apontando para o banco de producao.

O `--db-path` e' relativo: o servidor precisa ser lancado com o CWD na raiz do
repositorio, senao o caminho nao resolve.
