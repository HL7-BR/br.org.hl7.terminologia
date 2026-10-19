# Acerta a canonical_url das fontes do MS no OCL e mostra o resultado.
# Uso, na raiz do repositório:  powershell -ExecutionPolicy Bypass -File .\corrigir_urls.ps1
Set-Location $PSScriptRoot
$seguro = Read-Host "Token da API do OCL" -AsSecureString
$env:OCL_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro))
python atualizar_do_ocl.py --corrigir-urls 2>&1 | Tee-Object -FilePath ocl-urls.log
Remove-Item Env:OCL_TOKEN
Write-Host "`nResultado salvo em ocl-urls.log" -ForegroundColor Cyan
