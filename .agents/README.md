# Diretório `.agents/`

Configuração nativa do Antigravity e do Gemini CLI. Os arquivos aqui são
versionados porque `AGENTS.md` coloca `.agents/rules/` na hierarquia de
precedência de contratos — regra de precedência não pode viver em arquivo
ignorado.

| Subdiretório | Conteúdo |
|---|---|
| `hooks/` | Hooks de ciclo de vida (PowerShell, UTF-8 with BOM) |
| `rules/` | Regras modulares por subsistema, descobertas automaticamente |
| `workflows/` | Playbooks declarativos de execução sequencial |
| `agents/` | Definições de subagentes declarativos |

## Hooks — verificação pendente do caminho

`hooks.json` invoca os scripts por **caminho relativo**
(`hooks/PreToolUse-Guard.ps1`), na expectativa de que o runtime resolva a
partir de `.agents/`.

> [!IMPORTANT]
> **Isto ainda não foi verificado nesta máquina.** Se o Antigravity resolver o
> caminho a partir da raiz do workspace em vez de `.agents/`, o arquivo não é
> encontrado e **o guard simplesmente não roda** — sem erro visível. O modo de
> falha é silencioso e o resultado é uma proteção que parece ativa e não está,
> o que é pior do que não ter hook nenhum.
>
> Como verificar, uma vez: com os hooks ativos, peça ao agente uma edição em
> `.env`. O esperado é a recusa com a mensagem
> `BLOQUEADO POR ZERO-TRUST`. Se a edição passar, o caminho não resolveu — troque
> para `.agents/hooks/PreToolUse-Guard.ps1` nas duas entradas de `hooks.json`.

Caminhos absolutos não são alternativa: são proibidos pelo contrato do
repositório (`CLAUDE.md` § Caminhos).

## Limites conhecidos do `PreToolUse-Guard`

O guard casa nomes de arquivo no texto do comando. Ele **não** resolve
indireção por variável: `$f = '.env'; Set-Content $f x` passa, porque o nome
sensível nunca aparece literalmente no segmento inspecionado. A mesma limitação
existe no guard equivalente do Claude Code
(`.claude/hooks/Assert-SensitiveWriteGuard.ps1`) e é aceita conscientemente —
cobrir indireção exigiria interpretar o comando, não inspecioná-lo.

O guard é uma barreira contra erro acidental e descuido de agente, não contra
um ator que queira contorná-la deliberadamente.
