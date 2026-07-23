"""Sammelt Rohdaten: Windows-Eventlogs (via PowerShell), Systeminfo, Minidumps.

Einzige I/O-Schicht der Analyse. Jede Quelle degradiert einzeln — Ausfälle
landen als Klartext in bundle['limits'], die Analyse läuft weiter.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import subprocess
from datetime import datetime, timezone

from src import minidump

MINIDUMP_DIR = r"C:\Windows\Minidump"
MEMORY_DMP = r"C:\Windows\MEMORY.DMP"
PS_TIMEOUT = 180


class CollectorError(Exception):
    pass


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def build_ps_script(days: int) -> str:
    """Ein PowerShell-Skript, das alle Event-Quellen als ein JSON-Dokument liefert."""
    return r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$since = (Get-Date).AddDays(-%DAYS%)
$errors = New-Object System.Collections.ArrayList
function Norm($e, $withMessage) {
  $data = @{}
  try {
    $x = [xml]$e.ToXml()
    $i = 0
    foreach ($d in $x.Event.EventData.Data) {
      $i++
      if ($d -is [string]) { $data["param$i"] = $d }
      elseif ($d -is [System.Xml.XmlElement] -and $d.HasAttribute('Name')) {
        $data[$d.GetAttribute('Name')] = "$($d.InnerText)"
      }
      else { $data["param$i"] = "$($d.InnerText)" }
    }
  } catch {}
  $o = @{
    time = (Get-Date $e.TimeCreated).ToString("yyyy-MM-ddTHH:mm:sszzz")
    log = $e.LogName; provider = $e.ProviderName; id = $e.Id
    level = $e.Level; record = $e.RecordId; data = $data
  }
  if ($withMessage) { try { $o.message = $e.Message } catch { $o.message = $null } }
  $o
}
function Query($name, $filter, $withMessage) {
  try {
    $evs = Get-WinEvent -FilterHashtable $filter -ErrorAction Stop
    @($evs | ForEach-Object { Norm $_ $withMessage })
  } catch [Exception] {
    if ($_.Exception.Message -notmatch 'keine Ereignisse|No events were found') {
      [void]$errors.Add("$name : $($_.Exception.Message)")
    }
    @()
  }
}
$sys1 = Query 'System-Kernereignisse' @{LogName='System'; Id=41,1001,6008,6005,6006,1074,4101,7031,7034; StartTime=$since} $false
$sys2 = Query 'Hardware/Datentraeger' @{LogName='System'; ProviderName='disk','Ntfs','volmgr','storahci','stornvme','Microsoft-Windows-WHEA-Logger'; Level=1,2,3; StartTime=$since} $false
$memd = Query 'Speicherdiagnose' @{LogName='System'; ProviderName='Microsoft-Windows-MemoryDiagnostics-Results'; StartTime=(Get-Date).AddDays(-365)} $true
$upd  = Query 'Windows-Updates' @{LogName='System'; ProviderName='Microsoft-Windows-WindowsUpdateClient'; Id=19; StartTime=$since} $true
$app  = Query 'Programmabstuerze' @{LogName='Application'; ProviderName='Application Error','Application Hang'; StartTime=$since} $false
$system = @{}
try {
  $os = Get-CimInstance Win32_OperatingSystem
  $cs = Get-CimInstance Win32_ComputerSystem
  $isLaptop = $false
  try { $isLaptop = ($cs.PCSystemType -eq 2) -or ((Get-CimInstance Win32_Battery | Measure-Object).Count -gt 0) } catch {}
  $system = @{
    os_name = $os.Caption; os_version = $os.Version; build = $os.BuildNumber
    boot_time = (Get-Date $os.LastBootUpTime).ToString("yyyy-MM-ddTHH:mm:sszzz")
    ram_gb = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
    manufacturer = $cs.Manufacturer; model = $cs.Model
    is_laptop = $isLaptop; hostname = $env:COMPUTERNAME
  }
} catch { [void]$errors.Add("Systeminfo: $($_.Exception.Message)") }
$seen = @{}
$events = @()
foreach ($e in ($sys1 + $sys2)) {
  $k = "$($e.record)"
  if (-not $seen.ContainsKey($k)) { $seen[$k] = $true; $events += $e }
}
@{
  events = $events; app_events = $app; memdiag_events = $memd
  update_events = $upd; system = $system; errors = @($errors)
} | ConvertTo-Json -Depth 8 -Compress
'''.replace("%DAYS%", str(int(days)))


def _run_powershell(script: str) -> dict:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            capture_output=True, timeout=PS_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CollectorError(f"PowerShell-Aufruf fehlgeschlagen: {exc}") from exc
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0 and not out:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise CollectorError(f"PowerShell-Fehler (Exit {proc.returncode}): {err[:500]}")
    start = out.find("{")
    if start < 0:
        raise CollectorError(f"Keine JSON-Ausgabe von PowerShell: {out[:200]!r}")
    try:
        return json.loads(out[start:])
    except json.JSONDecodeError as exc:
        raise CollectorError(f"PowerShell-JSON unlesbar: {exc}") from exc


def _norm_events(raw) -> list[dict]:
    if raw is None:
        return []
    if isinstance(raw, dict):  # ConvertTo-Json macht aus 1-elementigen Arrays Objekte
        raw = [raw]
    out = []
    for e in raw:
        if not isinstance(e, dict) or "id" not in e:
            continue
        out.append({
            "time": e.get("time", ""),
            "log": e.get("log", ""),
            "provider": e.get("provider") or "",
            "id": int(e["id"]),
            "level": int(e["level"]) if e.get("level") else 4,
            "data": e.get("data") or {},
            **({"message": e.get("message")} if "message" in e else {}),
        })
    return out


def _scan_minidumps(minidump_dir: str, limits: list[str]) -> list[dict]:
    dumps: list[dict] = []
    try:
        entries = sorted(os.scandir(minidump_dir), key=lambda d: d.name)
    except FileNotFoundError:
        return dumps
    except PermissionError:
        limits.append(
            "Minidump-Ordner nicht lesbar (Administratorrechte erforderlich) — "
            "Bugcheck-Codes aus Dumps stehen nicht zur Verfügung."
        )
        return dumps
    for entry in entries:
        if not entry.name.lower().endswith(".dmp"):
            continue
        try:
            st = entry.stat()
            dumps.append({
                "path": entry.path,
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(),
                "bugcheck": minidump.read_bugcheck(entry.path),
            })
        except OSError as exc:
            dumps.append({"path": entry.path, "size": 0, "mtime": None,
                          "bugcheck": None, "error": str(exc)})
    return dumps


def collect(days: int = 30, run_ps=None, minidump_dir: str = MINIDUMP_DIR,
            memory_dmp: str = MEMORY_DMP) -> dict:
    run_ps = run_ps or (lambda script: _run_powershell(script))
    limits: list[str] = []

    payload: dict = {}
    try:
        payload = run_ps(build_ps_script(days)) or {}
    except CollectorError as exc:
        limits.append(f"Ereignisprotokolle nicht lesbar: {exc}")

    for err in payload.get("errors") or []:
        limits.append(str(err))

    admin = is_admin()
    dumps = _scan_minidumps(minidump_dir, limits)
    if not admin and not dumps and os.path.isdir(minidump_dir):
        pass  # Hinweis kam ggf. schon über PermissionError

    mem = None
    try:
        st = os.stat(memory_dmp)
        mem = {"path": memory_dmp, "size": st.st_size,
               "mtime": datetime.fromtimestamp(st.st_mtime).astimezone().isoformat()}
    except OSError:
        mem = None

    if not admin:
        limits.append(
            "Die App läuft ohne Administratorrechte — Speicherabbilder (Minidumps) "
            "und einige Prüftools sind damit nicht verfügbar."
        )

    return {
        "collected_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "days": days,
        "is_admin": admin,
        "system": payload.get("system") or {},
        "events": _norm_events(payload.get("events")),
        "app_events": _norm_events(payload.get("app_events")),
        "memdiag_events": _norm_events(payload.get("memdiag_events")),
        "update_events": _norm_events(payload.get("update_events")),
        "minidumps": dumps,
        "memory_dmp": mem,
        "limits": limits,
    }
