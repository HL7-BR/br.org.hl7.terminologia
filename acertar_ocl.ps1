# Acerta o OCL antes do pacote de terminologia:
# 1) canonical_url das fontes do MS; 2) versões com data trocadas por SemVer; 3) nova simulação.
# Uso, na raiz do repositório:  powershell -ExecutionPolicy Bypass -File .\acertar_ocl.ps1
Set-Location $PSScriptRoot
$seguro = Read-Host "Token da API do OCL" -AsSecureString
$env:OCL_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro))
Start-Transcript -Path ocl-acerto.log -Force | Out-Null
Write-Host "`n1/4 URLs canônicas" -ForegroundColor Cyan
python atualizar_do_ocl.py --corrigir-urls 2>&1 | Tee-Object -FilePath ocl-acerto.txt -Append
Write-Host "`n2/4 Plano das versões (nada é gravado ainda)" -ForegroundColor Cyan
python atualizar_do_ocl.py --semver --seco 2>&1 | Tee-Object -FilePath ocl-acerto.txt -Append
$ok = Read-Host "`nAplicar o plano das versões? (s/n)"
if ($ok -eq "s") {
  Write-Host "`n3/4 Aplicando" -ForegroundColor Cyan
  python atualizar_do_ocl.py --semver 2>&1 | Tee-Object -FilePath ocl-acerto.txt -Append
  Write-Host "`n4/4 Simulação do pacote" -ForegroundColor Cyan
  python atualizar_do_ocl.py --vs-todos --seco | Select-Object -Last 1
}
Stop-Transcript | Out-Null
Remove-Item Env:OCL_TOKEN
Write-Host "`nSaída registrada em ocl-acerto.txt" -ForegroundColor Cyan
