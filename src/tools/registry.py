"""Katalog der Onboard-Prüftools."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from src.tools import parsers

PS_DISK_HEALTH = r'''
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$disks = Get-PhysicalDisk | ForEach-Object {
  $r = $null; try { $r = $_ | Get-StorageReliabilityCounter } catch {}
  [pscustomobject]@{
    FriendlyName = $_.FriendlyName; MediaType = "$($_.MediaType)"
    HealthStatus = "$($_.HealthStatus)"; OperationalStatus = "$($_.OperationalStatus)"
    SizeGB = [math]::Round($_.Size / 1GB, 1)
    Wear = $r.Wear; ReadErrorsTotal = $r.ReadErrorsTotal; Temperature = $r.Temperature
  }
}
@($disks) | ConvertTo-Json -Compress
'''

PS_DRIVER_INVENTORY = r'''
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$drv = Get-CimInstance Win32_PnPSignedDriver |
  Where-Object { $_.DriverDate -and $_.DeviceName } | ForEach-Object {
    [pscustomobject]@{
      DeviceName = $_.DeviceName; DriverVersion = $_.DriverVersion
      DriverDate = (Get-Date $_.DriverDate).ToString("yyyy-MM-dd")
      Manufacturer = $_.Manufacturer
    }
  } | Sort-Object DriverDate -Descending | Select-Object -First 40
@($drv) | ConvertTo-Json -Compress
'''


@dataclass(frozen=True)
class ToolDef:
    id: str
    name: str
    description: str
    needs_admin: bool
    repairs: bool
    duration_hint: str
    kind: str                      # process | powershell | launch
    command: object                # list[str] | str (PS-Skript) | Callable[[dict], list[str]]
    parser: Callable[[str, int], dict]
    warning: str | None = field(default=None)


def _chkdsk_command(params: dict | None) -> list[str]:
    volume = (params or {}).get("volume", "C:")
    if not re.fullmatch(r"[A-Za-z]:", volume):
        raise ValueError(f"Ungültiges Laufwerk: {volume!r}")
    return ["chkdsk", volume]


_TOOLS: list[ToolDef] = [
    ToolDef(
        id="sfc", name="Systemdateien prüfen (SFC)",
        description="Prüft alle geschützten Windows-Systemdateien und repariert "
                    "beschädigte Dateien automatisch aus dem Komponentenspeicher.",
        needs_admin=True, repairs=True, duration_hint="5–15 Minuten",
        kind="process", command=["sfc", "/scannow"], parser=parsers.parse_sfc,
    ),
    ToolDef(
        id="dism_scan", name="Windows-Abbild prüfen (DISM)",
        description="Prüft den Windows-Komponentenspeicher auf Beschädigungen. "
                    "Nur Prüfung — es wird nichts verändert.",
        needs_admin=True, repairs=False, duration_hint="2–10 Minuten",
        kind="process",
        command=["DISM.exe", "/Online", "/Cleanup-Image", "/ScanHealth"],
        parser=parsers.parse_dism,
    ),
    ToolDef(
        id="dism_restore", name="Windows-Abbild reparieren (DISM)",
        description="Repariert den Komponentenspeicher und lädt bei Bedarf intakte "
                    "Dateien von Windows Update nach.",
        needs_admin=True, repairs=True, duration_hint="10–30 Minuten",
        kind="process",
        command=["DISM.exe", "/Online", "/Cleanup-Image", "/RestoreHealth"],
        parser=parsers.parse_dism,
        warning="Verändert Systemdateien (Reparatur). Benötigt meist Internetzugang.",
    ),
    ToolDef(
        id="chkdsk", name="Datenträger prüfen (CHKDSK)",
        description="Prüft das Dateisystem nur lesend — ohne Neustart und ohne "
                    "Änderungen am Datenträger.",
        needs_admin=True, repairs=False, duration_hint="1–10 Minuten",
        kind="process", command=_chkdsk_command, parser=parsers.parse_chkdsk,
    ),
    ToolDef(
        id="memdiag_start", name="Arbeitsspeicher testen",
        description="Startet die Windows-Speicherdiagnose. Der Test läuft vor dem "
                    "Windows-Start; das Ergebnis erscheint danach in dieser App.",
        needs_admin=True, repairs=False, duration_hint="Neustart + 10–30 Minuten",
        kind="launch", command=["mdsched.exe"], parser=parsers.parse_memdiag_start,
        warning="Windows fragt nach dem Start, ob sofort neu gestartet werden soll — "
                "offene Arbeit vorher speichern.",
    ),
    ToolDef(
        id="disk_health", name="Datenträger-Gesundheit (SMART)",
        description="Liest Gesundheitsstatus, Abnutzung, Fehlerzähler und Temperatur "
                    "aller SSDs und Festplatten.",
        needs_admin=False, repairs=False, duration_hint="wenige Sekunden",
        kind="powershell", command=PS_DISK_HEALTH, parser=parsers.parse_disk_health,
    ),
    ToolDef(
        id="driver_inventory", name="Treiber-Inventar",
        description="Listet die zuletzt geänderten Gerätetreiber. Hilfreich, wenn die "
                    "Abstürze nach einem Treiber-Update begannen.",
        needs_admin=False, repairs=False, duration_hint="10–30 Sekunden",
        kind="powershell", command=PS_DRIVER_INVENTORY,
        parser=parsers.parse_driver_inventory,
    ),
]


def all_tools() -> list[ToolDef]:
    return list(_TOOLS)


def get_tool(tool_id: str) -> ToolDef:
    for t in _TOOLS:
        if t.id == tool_id:
            return t
    raise KeyError(tool_id)
