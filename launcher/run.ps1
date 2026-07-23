# Crash Analyzer Launcher
# 1) Versucht Selbst-Elevation (UAC) - Abbruch => Weiterlauf ohne Admin
# 2) Legt bei Bedarf die venv an und installiert Abhaengigkeiten
# 3) Wendet ein vorbereitetes Update an (Staging)
# 4) Startet die App (natives Fenster)
param(
    [switch]$NoElevate,
    [string]$AppArgs = ""
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Write-Step($msg) { Write-Host "[Crash Analyzer] $msg" }

# --- 1) Elevation ---
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin -and -not $NoElevate) {
    Write-Step "Fordere Administratorrechte an (fuer Minidumps und Prueftools) ..."
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"")
    if ($AppArgs) { $argList += @('-AppArgs', "`"$AppArgs`"") }
    try {
        Start-Process -FilePath 'powershell.exe' -ArgumentList $argList -Verb RunAs | Out-Null
        exit 0
    } catch {
        Write-Step "Ohne Administratorrechte fortgesetzt (eingeschraenkte Prueftools)."
    }
}

# --- 2) venv-Bootstrap ---
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Step "Erster Start: Python-Umgebung wird eingerichtet (einmalig, braucht Internet) ..."
    $sysPython = $null
    foreach ($cand in @('py', 'python')) {
        try {
            $null = & $cand --version 2>$null
            if ($LASTEXITCODE -eq 0) { $sysPython = $cand; break }
        } catch {}
    }
    if (-not $sysPython) {
        Write-Host ""
        Write-Host "FEHLER: Python 3.10+ wurde nicht gefunden." -ForegroundColor Red
        Write-Host "Bitte von https://www.python.org/downloads/ installieren (Haken bei 'Add to PATH')."
        exit 1
    }
    if ($sysPython -eq 'py') { & py -3 -m venv "$root\.venv" } else { & python -m venv "$root\.venv" }
    if (-not (Test-Path $venvPython)) {
        Write-Host "FEHLER: Die Python-Umgebung konnte nicht angelegt werden." -ForegroundColor Red
        exit 1
    }
    Write-Step "Installiere Abhaengigkeiten ..."
    & $venvPython -m pip install --disable-pip-version-check -q -r "$root\requirements.txt"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FEHLER: Abhaengigkeiten konnten nicht installiert werden (Internet?)." -ForegroundColor Red
        exit 1
    }
}

# --- 3) Vorbereitetes Update anwenden ---
if (Test-Path (Join-Path $root '_staging\update.zip')) {
    Write-Step "Installiere vorbereitetes Update ..."
    & $venvPython -m src.updater --apply
    # Exit-Code 1 = kein/fehlgeschlagenes Update; Meldung kam vom Updater, App startet trotzdem
}

# --- 4) App starten ---
Write-Step "Starte App ..."
if ($AppArgs) {
    & $venvPython -m src.app $AppArgs.Split(' ')
} else {
    & $venvPython -m src.app
}
exit $LASTEXITCODE
