# Cria no OCL (org HL7) o CodeSystem v2-0443 (Provider role) e o ValueSet
# immunization-function do FHIR R4, a partir dos JSON oficiais desta pasta.
# Mesmo plano do importar_ocl.py, sem precisar de Python.
#
# Uso (PowerShell, de qualquer pasta):
#   powershell -ExecutionPolicy Bypass -File .\ocl\HL7-v2-0443\importar_ocl.ps1              # plano, confirma, pede o token e cria
#   powershell -ExecutionPolicy Bypass -File .\ocl\HL7-v2-0443\importar_ocl.ps1 -Seco        # só o plano (sem token)
#   powershell -ExecutionPolicy Bypass -File .\ocl\HL7-v2-0443\importar_ocl.ps1 -SoConferir  # só confere
#
# O token é pedido sem eco, fica só na memória e não é gravado.
# Autoria: Jussara Macedo Pinho Rötzsch.
param([switch]$Seco, [switch]$SoConferir)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Set-Location $PSScriptRoot

$API = if ($env:OCL_API) { $env:OCL_API } else { "https://oclapi2.ips.hsl.org.br" }
$CS = Get-Content -Raw -Encoding UTF8 "v2-0443.cs.json" | ConvertFrom-Json
$VS = Get-Content -Raw -Encoding UTF8 "valueset-immunization-function.json" | ConvertFrom-Json

$FONTE = "/orgs/HL7/sources/v2-0443/"
$COLECAO = "/orgs/HL7/collections/immunization-function/"
$VERSAO_FONTE = "2.9.0"          # CodeSystem 2.9, em SemVer como as outras v2 do OCL
$VERSAO_COLECAO = $VS.version    # 4.0.1
$script:Token = $null

function Chamar($Metodo, $Caminho, $Corpo = $null) {
    $h = @{}
    if ($script:Token) { $h["Authorization"] = "Token " + $script:Token }
    $p = @{ Uri = $API + $Caminho; Method = $Metodo; Headers = $h; UseBasicParsing = $true }
    if ($null -ne $Corpo) {
        $p["Body"] = [Text.Encoding]::UTF8.GetBytes(($Corpo | ConvertTo-Json -Depth 10 -Compress))
        $p["ContentType"] = "application/json; charset=utf-8"
    }
    try {
        $r = Invoke-WebRequest @p
        $txt = [Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray())
        $dados = if ($txt.Trim()) { $txt | ConvertFrom-Json } else { $null }
        return @{ St = [int]$r.StatusCode; Dados = $dados }
    } catch {
        $st = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
        return @{ St = $st; Dados = "$($_.ErrorDetails.Message) $($_.Exception.Message)" }
    }
}

function Existe($Caminho) { (Chamar GET $Caminho).St -eq 200 }

function Expressoes {
    $inc = @($VS.compose.include)
    if ($inc.Count -ne 1 -or $inc[0].system -ne $CS.url) { throw "compose inesperado no ValueSet" }
    @($inc[0].concept | ForEach-Object { $FONTE + "concepts/$($_.code)/" })
}

function Plano {
    Write-Host "API: $API"
    Write-Host "Fonte $FONTE ($($CS.title)): $(if (Existe $FONTE) { 'JÁ EXISTE' } else { 'nova' })"
    Write-Host "  $(@($CS.concept).Count) conceitos: $((@($CS.concept) | ForEach-Object { $_.code }) -join ', ')"
    Write-Host "  versão $VERSAO_FONTE liberada"
    Write-Host "Coleção $COLECAO ($($VS.title)): $(if (Existe $COLECAO) { 'JÁ EXISTE' } else { 'nova' })"
    Write-Host "  referências: $((Expressoes) -join ', ')"
    Write-Host "  versão $VERSAO_COLECAO liberada"
}

function Ok($Rotulo, $R) {
    if ($R.St -in 200, 201) { Write-Host "${Rotulo}: $($R.St)" }
    else { Write-Host "${Rotulo}: $($R.St) $("$($R.Dados)".Substring(0, [Math]::Min(400, "$($R.Dados)".Length)))" -ForegroundColor Red; throw "Parado no primeiro erro." }
}

function Importar {
    $u = Chamar GET "/user/"
    if ($u.St -ne 200) { throw "Token recusado ($($u.St))." }
    Write-Host "Usuário: $($u.Dados.username)"
    if ((Existe $FONTE) -or (Existe $COLECAO)) { throw "Fonte ou coleção já existe; nada foi feito. Rode com -SoConferir." }

    Ok "POST fonte" (Chamar POST "/orgs/HL7/sources/" @{
        id = "v2-0443"; short_code = "v2-0443"; name = $CS.name; full_name = $CS.title
        source_type = "Dictionary"; canonical_url = $CS.url; default_locale = "en"; supported_locales = "en"
        description = $CS.description; public_access = "View"; case_sensitive = $true; version_needed = $true })
    foreach ($c in @($CS.concept)) {
        Ok "POST conceito $($c.code)" (Chamar POST ($FONTE + "concepts/") @{
            id = $c.code; concept_class = "Misc"; datatype = "Text"
            names = @(@{ name = $c.display.Trim(); locale = "en"; locale_preferred = $true; name_type = "Fully Specified" }) })
    }
    Ok "POST versão $VERSAO_FONTE" (Chamar POST ($FONTE + "versions/") @{
        id = $VERSAO_FONTE; released = $true
        description = "HL7 v2 table 0443 (Provider role), CodeSystem $($CS.version) do FHIR R4" })

    Ok "POST coleção" (Chamar POST "/orgs/HL7/collections/" @{
        id = "immunization-function"; short_code = "immunization-function"; name = $VS.name; full_name = $VS.title
        collection_type = "Value Set"; canonical_url = $VS.url; default_locale = "en"; supported_locales = "en"
        description = $VS.description; public_access = "View"; autoexpand_head = $true })
    Ok "PUT referências" (Chamar PUT ($COLECAO + "references/?cascade=none") @{ data = @{ expressions = @(Expressoes) } })
    Ok "POST versão $VERSAO_COLECAO" (Chamar POST ($COLECAO + "versions/") @{
        id = $VERSAO_COLECAO; released = $true; description = "$($VS.title) do FHIR R4 ($VERSAO_COLECAO)" })
}

function Conferir {
    $erros = 0
    $r = Chamar GET ($FONTE + "concepts/?limit=100")
    $ocl = @{}
    if ($r.St -eq 200) { foreach ($c in @($r.Dados)) { $ocl[$c.id] = $c.display_name } }
    foreach ($c in @($CS.concept)) {
        if ($ocl[$c.code] -cne $c.display.Trim()) { $erros++; Write-Host "FALTA conceito: $($c.code) $($c.display.Trim()) | OCL: $($ocl[$c.code])" }
    }
    $r = Chamar GET ($FONTE + "versions/")
    if ($r.St -ne 200 -or -not (@($r.Dados) | Where-Object { $_.id -eq $VERSAO_FONTE -and $_.released })) { $erros++; Write-Host "FALTA versão liberada $VERSAO_FONTE da fonte" }
    $r = Chamar GET ($COLECAO + "references/?limit=100")
    $tem = if ($r.St -eq 200) { @($r.Dados | ForEach-Object { $_.expression }) } else { @() }
    foreach ($e in Expressoes) { if ($tem -notcontains $e) { $erros++; Write-Host "FALTA referência: $e" } }
    $r = Chamar GET ($COLECAO + "versions/")
    if ($r.St -ne 200 -or -not (@($r.Dados) | Where-Object { $_.id -eq $VERSAO_COLECAO -and $_.released })) { $erros++; Write-Host "FALTA versão liberada $VERSAO_COLECAO da coleção" }
    foreach ($q in "/fhir/CodeSystem/?url=$($CS.url)", "/fhir/ValueSet/?url=$($VS.url)") {
        $r = Chamar GET $q
        Write-Host "FHIR ${q}: $($r.St), total $(if ($r.St -eq 200) { $r.Dados.total })"
    }
    Write-Host "Conferência: $(if ($erros -eq 0) { 'OK' } else { "$erros problema(s)" })" -ForegroundColor $(if ($erros -eq 0) { "Green" } else { "Red" })
}

if ($Seco) { Plano; exit }
if ($SoConferir) { Conferir; exit }

Plano
if ((Read-Host "`nCriar no OCL? (s/n)") -ne "s") { exit }
$seguro = Read-Host "Token da API do OCL" -AsSecureString
$script:Token = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro))
Start-Transcript -Path (Join-Path $PSScriptRoot "importacao.txt") -Force | Out-Null
try { Importar; Conferir }
catch { Write-Host $_.Exception.Message -ForegroundColor Red }
finally { Stop-Transcript | Out-Null; $script:Token = $null }
Write-Host "`nSaída registrada em $(Join-Path $PSScriptRoot 'importacao.txt')" -ForegroundColor Cyan
