# Signiert die CrashAnalyzer.exe (Authenticode + Zeitstempel).
#
# Standard: nimmt das Code-Signing-Zertifikat "CN=Alexander May" aus dem
# Benutzer-Zertifikatspeicher (Cert:\CurrentUser\My). Mit einem gekauften
# Zertifikat (Certum/Sectigo/DigiCert auf Token, oder Azure Trusted Signing)
# einfach dessen Thumbprint uebergeben:
#
#   .\build\sign.ps1                       # Standard-Zertifikat, dist\CrashAnalyzer.exe
#   .\build\sign.ps1 -Thumbprint ABC123... # bestimmtes Zertifikat
#   .\build\sign.ps1 -Path andere.exe
param(
    [string]$Thumbprint = "",
    [string]$Path = "",
    [string]$TimestampServer = "http://timestamp.digicert.com"
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $Path) { $Path = Join-Path $root 'dist\CrashAnalyzer.exe' }
if (-not (Test-Path $Path)) { throw "Datei nicht gefunden: $Path" }

if ($Thumbprint) {
    $cert = Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\My -ErrorAction SilentlyContinue |
        Where-Object { $_.Thumbprint -eq $Thumbprint } | Select-Object -First 1
    if (-not $cert) { throw "Kein Zertifikat mit Thumbprint $Thumbprint gefunden." }
} else {
    $cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Subject -like '*Alexander May*' } |
        Sort-Object NotAfter -Descending | Select-Object -First 1
    if (-not $cert) { throw "Kein Code-Signing-Zertifikat gefunden. Erst anlegen oder -Thumbprint angeben." }
}

Write-Host "Signiere $Path"
Write-Host "  Zertifikat: $($cert.Subject)  (gueltig bis $($cert.NotAfter.ToString('yyyy-MM-dd')))"
$result = Set-AuthenticodeSignature -FilePath $Path -Certificate $cert `
    -TimestampServer $TimestampServer -HashAlgorithm SHA256
Write-Host "  Status: $($result.Status) - $($result.StatusMessage)"
if ($result.Status -eq 'Valid') {
    Write-Host "Signatur gueltig (Zertifikatskette wird auf diesem Rechner vertraut)." -ForegroundColor Green
} elseif ($result.Status -eq 'UnknownError' -and $result.SignerCertificate) {
    Write-Host "Signatur angebracht; Kette (noch) nicht vertraut - bei selbstsigniertem Zertifikat normal." -ForegroundColor Yellow
}
