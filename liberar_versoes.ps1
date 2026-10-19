# Libera a versão nas fontes do OCL sem versão liberada e refaz a simulação.
# Uso, na raiz do repositório:  .\liberar_versoes.ps1
# O token é pedido na tela e não aparece nem fica gravado.
param([string]$Versao = "2026-10-19")
Set-Location $PSScriptRoot
$seguro = Read-Host "Token da API do OCL" -AsSecureString
$env:OCL_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro))
Write-Host "`n1/3 Simulação (atualiza o relatório)" -ForegroundColor Cyan
python atualizar_do_ocl.py --vs-todos --seco | Select-Object -Last 1
Write-Host "`n2/3 Liberando a versão $Versao" -ForegroundColor Cyan
python atualizar_do_ocl.py --liberar $Versao
Write-Host "`n3/3 Simulação depois da liberação" -ForegroundColor Cyan
python atualizar_do_ocl.py --vs-todos --seco | Select-Object -Last 1
Remove-Item Env:OCL_TOKEN
