?# ==============================================================================
# ARQUIVO: ConfigurarEmailTeste.ps1
# DESCRICAO: Define ou remove o e-mail de redirecionamento para modo de teste.
# ==============================================================================

param(
    [Parameter(Mandatory = $false)]
    [string]$Email = "gabriel.dias@costaricamalhas.ind.br",

    [Parameter(Mandatory = $false)]
    [switch]$Remover
)

if ($Remover) {
    Write-Host "Removendo variavel AUTOMACAO_TEST_EMAIL..." -ForegroundColor Yellow
    [Environment]::SetEnvironmentVariable("AUTOMACAO_TEST_EMAIL", $null, "User")
    $env:AUTOMACAO_TEST_EMAIL = $null
    Write-Host "[OK] Variavel removida. Modo Producao ativo." -ForegroundColor Green
}
else {
    Write-Host "Configurando AUTOMACAO_TEST_EMAIL para: $Email" -ForegroundColor Cyan
    [Environment]::SetEnvironmentVariable("AUTOMACAO_TEST_EMAIL", $Email, "User")
    $env:AUTOMACAO_TEST_EMAIL = $Email
    Write-Host "[OK] Variavel definida com sucesso." -ForegroundColor Green
    Write-Host "OBSERVACAO: O Monitor foi reiniciado automaticamente pelo arquivo .bat." -ForegroundColor Yellow
}

