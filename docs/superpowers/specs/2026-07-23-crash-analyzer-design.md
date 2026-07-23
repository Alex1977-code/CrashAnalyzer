# Crash Analyzer — Design v2 (2026-07-23)

> v2 nach User-Vorgabe mitten in der Session: „beste App, professionelles GUI und beste
> Technologie, updatebar, Prüftools onboard" — vom statischen Report (v1) zur
> vollwertigen Desktop-App aufgestuft.

## Ziel

Eine professionelle Windows-Desktop-App, die nach einem Absturz gestartet wird, die
Absturz-Historie analysiert und dem Benutzer **auf Deutsch und in Klartext** erklärt:

1. **Was** ist passiert (Bluescreen, plötzlicher Stromverlust, eingefroren, unerwarteter Neustart, …)
2. **Warum** vermutlich (wahrscheinlichste Ursache mit Konfidenz, plus Alternativen)
3. **Was tun** (priorisierte Handlungsempfehlungen — und die passenden **Prüftools direkt in der App ausführbar**)

Zielgruppe: auch Nicht-Techniker. Technische Details (Event-IDs, Bugcheck-Parameter,
Dump-Pfade) vorhanden, aber einklappbar.

## Anforderungen (User)

- Beste App / professionelles GUI / beste Technologie
- **Updatebar** (App kann sich selbst aktualisieren)
- **Prüftools onboard** (Diagnosen direkt aus der App starten, nicht nur empfehlen)

## Getroffene Annahmen (autonome Session, Defaults)

- Windows 10/11, deutschsprachig; analysiert den Rechner, auf dem sie läuft.
- Python 3.10+ auf der Zielmaschine (hier: 3.12, MS-Store). App läuft aus eigener venv,
  Launcher bootstrappt sie beim ersten Start (Internet nötig nur beim ersten Start/Update).
- „Rechner abgestürzt" = Systemebene; Programmabstürze als Sekundär-Sektion.
- Prüftools starten nur auf expliziten Klick des Benutzers; reparierende Aktionen
  (DISM RestoreHealth, chkdsk /f) sind klar als solche gekennzeichnet.

## Technologie-Entscheidung

**Gewählt: FastAPI (Python) + natives WebView2-Fenster (pywebview) + handgebautes
modernes Web-Frontend (ES-Module, ohne Node-Build).**

- FastAPI/uvicorn: moderner, typisierter API-Standard; Engine bleibt reine Python-Logik → voll testbar.
- pywebview über den auf Win11 vorinstallierten Edge-WebView2 → echtes App-Fenster,
  kein Browser-Tab; `--browser`-Fallback vorhanden.
- Frontend ohne npm-Buildkette: professionelles UI mit modernem CSS/ES-Modulen; die App
  bleibt per Datei-Kopie updatebar, keine Toolchain-Abhängigkeit (Sophos-Umgebung!).
- Verworfen: Electron/Tauri (Toolchain-Gewicht), reines PowerShell/WPF (schwer testbar),
  statischer HTML-Report (v1 — erfüllt „professionelles GUI/Prüftools" nicht).

## Architektur

```
Crash_Analyzer/
  CrashAnalyzer.bat            Doppelklick-Einstieg
  launcher/run.ps1             UAC-Selbst-Elevation (Abbruch ⇒ ohne Admin weiter),
                               venv-Bootstrap, Staged-Update anwenden, App starten
  VERSION  config.json         Version; Einstellungen inkl. Update-Feed-URL, Zeitfenster
  requirements.txt
  src/
    app.py                     Einstieg: uvicorn-Thread + pywebview-Fenster (--browser, --port)
    api.py                     REST: /api/analysis, /api/tools…, /api/update…, /api/config
    collector.py               Get-WinEvent/CIM via PowerShell → JSON (einzige I/O-Schicht)
    minidump.py                Bugcheck direkt aus .dmp-Headern (PAGEDU64/PAGEDUMP)
    engine.py                  PURE: Events → Episoden → Klassifikation → Muster → Konfidenz
    knowledge.py  kb/*.json    Wissensbasis: Bugcheck-Codes, Ursachen, Empfehlungen (deutsch)
    updater.py                 Feed prüfen, Download, SHA256, Staging (Launcher wendet an)
    tools/                     Prüftools: registry.py, runner.py + je Tool Definition+Parser
    web/                       index.html, css/, js/ (Dashboard, Prüftools, Einstellungen)
  tests/                       pytest: Engine-Fixtures, Parser, Updater, API (httpx)
```

## Datenquellen (collector) — unverändert aus v1

System-Log: 41 (Kernel-Power, EventData `BugcheckCode`/`PowerButtonTimestamp`), 1001
(BugCheck: Code, Parameter, Dump-Pfad), 6008, 6005/6006/1074 (Abgrenzung), WHEA-Logger
17–20/47, disk/Ntfs/stor* 7/11/51/55/129/153/157, Display 4101 (TDR), SCM 7031/7034,
WindowsUpdateClient 19. Application-Log: 1000/1002 (+ MemoryDiagnostics-Results 1201/1202).
Minidumps: `C:\Windows\Minidump\*.dmp`, `MEMORY.DMP` (Header-Parsing, braucht Admin).
CIM: OS/ComputerSystem/Enclosure (RAM, Uptime, Modell, Laptop-Erkennung).
Strukturiert via `ToXml()`/EventData (keine lokalisierten Message-Strings), Fenster
Standard 30 Tage, pro Quelle graceful degradieren; Lücken erscheinen im UI unter „Grenzen".

## Analyse (engine) — unverändert aus v1

1. Anker 41/6008 → Episoden (±5-min-Dedupe), 1001/Dumps zeitlich zuordnen.
2. Indizienfenster 24 h davor / 15 min danach (WHEA, Disk, TDR, Dienste).
3. Präzedenz: Bugcheck-Code → **Bluescreen** (Wissensbasis) · `PowerButtonTimestamp≠0` →
   **Power-Taste/eingefroren** · WHEA-fatal → **Hardware** · Disk-Cluster → **Datenträger** ·
   sonst → **Stromverlust/Hard-Off** mit Differenzialhinweisen.
4. Muster: Häufung ≥3/7 Tage, gleicher Code mehrfach, Beginn nach Update/Datum, Tageszeit.
5. Konfidenz hoch/mittel/niedrig, im UI benannt.

Wissensbasis: ~22 häufigste Bugcheck-Codes (0xA, 0x1A, 0x1E, 0x24, 0x3B, 0x50, 0x7A, 0x7E,
0x9F, 0xC2, 0xD1, 0xEF, 0xF4, 0x101, 0x116, 0x119, 0x124, 0x133, 0x139, 0x13A, 0x154, 0xFE)
mit Klartext + Empfehlungs-Verweisen, generischer Fallback. Empfehlungen gestuft:
Sofort → Diagnose (verlinkt aufs Onboard-Prüftool!) → Hardware → wann zum Profi.

## Prüftools onboard (tools/)

Einheitliches Modell: `ToolDef` (id, Name, Beschreibung deutsch, braucht-Admin,
Dauer-Schätzung, reparierend ja/nein) + Runner (Subprozess im Hintergrund-Thread,
Live-Output gepuffert, Abbruch möglich) + Parser (Rohausgabe → Verdikt
ok/warnung/problem + Klartext) . API: Start → Run-ID, Polling liefert Output-Delta +
Status + Ergebnis. Ein Lauf pro Tool gleichzeitig; Ergebnisse fließen in die
Empfehlungs-Sektion zurück („SFC fand beschädigte Dateien → …").

| Tool | Kommando | Admin | Art |
|---|---|---|---|
| Systemdateien-Prüfung | `sfc /scannow` | ja | prüfend/reparierend |
| Windows-Abbild prüfen | `DISM /Online /Cleanup-Image /ScanHealth` | ja | prüfend |
| Windows-Abbild reparieren | `DISM … /RestoreHealth` | ja | reparierend (gekennzeichnet) |
| Datenträger prüfen | `chkdsk <vol:>` (nur lesend) | ja | prüfend |
| Speicherdiagnose | `mdsched.exe` starten (Windows-Dialog) + letzte Ergebnisse aus Eventlog 1201/1202 | Start: ja | prüfend (Neustart) |
| Datenträger-Gesundheit | Get-PhysicalDisk + StorageReliabilityCounter + SMART-Status | teils | lesend |
| Treiber-Inventar | pnputil /enum-drivers (jüngste zuerst, Korrelation zu Absturzbeginn) | nein | lesend |

## Updatebarkeit (updater.py + Launcher)

- `VERSION` (semver) + `config.json:update.feed_url` (Standard: leer ⇒ UI zeigt
  „kein Update-Feed konfiguriert" mit Erklärung; vorbereitet für GitHub-Releases-URL o. ä.).
- Feed-Format: JSON `{version, zip_url, sha256, notes}`.
- Ablauf: „Nach Updates suchen" → Vergleich → Download nach `_staging/` → SHA256-Prüfung →
  Hinweis „wird beim nächsten Start installiert". Launcher: wenn `_staging/` valide →
  Backup nach `_backup/` → Dateien ersetzen (venv/config/Backups ausgenommen) → bei Fehler
  Rollback aus Backup. Kein Selbst-Überschreiben laufender Prozesse.
- Wissensbasis (`kb/*.json`) ist Teil des Update-Pakets, damit neue Bugcheck-Einträge ohne
  Code-Release verteilbar wären.

## GUI (web/)

Seiten: **Diagnose** (Diagnose-Kopf mit Kernaussage, Episoden-Karten Was/Warum/Konfidenz/
Empfehlungen mit Tool-Buttons, Zeitleiste 30 Tage, Programmabstürze, Grenzen der Analyse) ·
**Prüftools** (Karten mit Status/letztem Ergebnis, Live-Konsole beim Lauf) ·
**Einstellungen/Update** (Zeitfenster, Feed-URL, Update-Status, Version).
Deutsch, professionelles Design, Dark/Light nach System, technische Details einklappbar.
Bei 0 Episoden: „Keine Systemabstürze gefunden"-Zustand mit Erklärung + App-Abstürzen.
Vor Chart-Implementierung wird der dataviz-Skill geladen (Zeitleisten-Design).

## Fehlerbehandlung

- Ohne Admin: Analyse läuft (Events lesbar); Minidumps/Admin-Tools zeigen klaren
  „Als Administrator neu starten"-Hinweis; UAC-Abbruch im Launcher wird gefangen.
- Jede Collector-Quelle einzeln degradierbar; Sammelfehler → „Grenzen"-Sektion, nie Abbruch.
- Tool-Subprozesse: Timeout, Abbruch-Endpoint, Exit-Code + Parser-Fallback (Rohtext zeigen).
- Update: Hash-Mismatch ⇒ Staging verwerfen; Apply-Fehler ⇒ Rollback; alles geloggt.

## Tests

- Engine/Wissensbasis: pytest mit JSON-Fixtures (BSOD-mit-Code, nacktes 41, Power-Taste,
  WHEA, Disk-Cluster, TDR→0x116, stabiler Rechner, Muster-Fälle).
- minidump.py: synthetische PAGEDU64-Datei; Tool-Parser: aufgezeichnete Beispielausgaben
  (deutsch/englisch); updater.py: lokaler Feed + Staging/Rollback; API: httpx-TestClient.
- Integration: Live-Lauf auf dieser Maschine (erwartet: 0 Episoden, ~8 App-Crashes),
  GUI-Verifikation im Browser, Prüftool-Probelauf (Treiber-Inventar/Disk-Health ohne Admin).
