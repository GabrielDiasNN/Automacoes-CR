#
# Trava da forma canonica de bootstrap do lib/python nos scripts de automacao
# (achado A4 da revisao arquitetural).
#
# DECISAO REGISTRADA: os scripts de extracao mantem UMA linha de
# `sys.path.insert` apontando para `lib/python`. A alternativa — empacotar
# `lib/python` e instalar com `pip install -e .` — foi avaliada e recusada:
# tornaria os scripts nao executaveis diretamente (`python extract_oracle.py`,
# como os devs depuram hoje) sem uma instalacao previa no interpretador, e uma
# instalacao ausente falharia silenciosamente no proximo cron das automacoes de
# producao. O custo de uma linha por script e menor que esse risco.
#
# O que este teste protege e o que sobrou do achado: as cinco ocorrencias devem
# permanecer IDENTICAS. A proliferacao real (blocos repetidos dentro do mesmo
# arquivo, variantes divergentes) foi eliminada; o drift e o que traria ela de
# volta.
#

$ScriptsComBootstrap = @(
    "Receitas Bloqueadas\processar_receitas.py",
    "Receitas Emitidas\extract_oracle.py",
    "Montagem de Terceirizados\extract_oracle.py",
    "OBs Paradas Fase\extract_obs.py",
    "OBs Fluxo Sem Tingimento\extract_ofst.py"
)

BeforeAll {
    $script:RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

    # Forma canonica, normalizada (sem espacos em branco irrelevantes).
    $script:FormaCanonica = 'sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","lib","python"))'

    function Get-NormalizedContent {
        param([string]$RelativePath)

        # O bootstrap e quebrado em varias linhas pelo black; comparar sem
        # whitespace torna o teste imune a reformatacao e sensivel apenas ao
        # conteudo real da chamada.
        $conteudo = Get-Content -LiteralPath (Join-Path $script:RepoRoot $RelativePath) -Raw
        return ($conteudo -replace '\s', '')
    }
}

Describe "Bootstrap do lib/python nos scripts de automacao" {
    It "<_> usa a forma canonica de bootstrap" -ForEach $ScriptsComBootstrap {
        Get-NormalizedContent -RelativePath $_ | Should -BeLike "*$($script:FormaCanonica)*"
    }

    It "<_> declara o bootstrap do lib/python uma unica vez" -ForEach $ScriptsComBootstrap {
        # OBs Fluxo Sem Tingimento tem um segundo insert (o proprio diretorio,
        # para os modulos locais models/errors/queries); a contagem abaixo mede
        # apenas o bootstrap do lib/python.
        $normalizado = Get-NormalizedContent -RelativePath $_
        @([regex]::Matches($normalizado, [regex]::Escape($script:FormaCanonica))).Count |
            Should -Be 1
    }
}
