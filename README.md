# Crash Analyzer

Windows-Desktop-App, die nach einem Absturz analysiert, **was** passiert ist,
**warum** (mit Konfidenz), und **was zu tun ist** — auf Deutsch, auch für
Nicht-Techniker. Diagnose-Prüftools sind direkt eingebaut, die App kann sich
selbst aktualisieren. Alle Daten bleiben auf dem Rechner.

## Start

Doppelklick auf **`CrashAnalyzer.bat`**.

- Beim ersten Start wird einmalig eine Python-Umgebung eingerichtet (braucht
  Internet und ein installiertes Python 3.10+).
- Die Administrator-Abfrage (UAC) bestätigen — nur dann sind Minidump-Analyse
  und die System-Prüftools (SFC, DISM, CHKDSK, Speicherdiagnose) verfügbar.
  Bei „Nein" läuft die App eingeschränkt weiter.
- Es öffnet sich ein natives App-Fenster (WebView2). Alternativ:
  `python -m src.app --browser` (Standardbrowser) oder `--no-window` (nur Server).

## Was analysiert wird

| Quelle | Zweck |
|---|---|
| System-Ereignisprotokoll (Kernel-Power 41, BugCheck 1001, 6008, WHEA, disk/Ntfs, Display 4101 …) | Absturz-Episoden finden und klassifizieren |
| Anwendungs-Ereignisprotokoll (1000/1002) | Programmabstürze (Sekundärbefund) |
| `C:\Windows\Minidump\*.dmp`, `MEMORY.DMP` | Stopcode direkt aus dem Dump-Header (Admin nötig) |
| Systeminfo (CIM) | Kontext: Modell, RAM, Laufzeit, Laptop-Erkennung |

Jeder Absturz wird als Karte erklärt: Bluescreen (mit Stopcode-Wissensbasis,
~22 häufigste Codes), plötzlicher Stromverlust, Power-Taste/eingefroren,
Hardware- oder Datenträger-Verdacht — inklusive Indizien, Konfidenz und
priorisierten Empfehlungen mit direktem Sprung zum passenden Prüftool.
Muster über mehrere Abstürze (Häufung, gleicher Code, Beginn nach Update,
gleiche Uhrzeit) werden separat ausgewiesen.

## Prüftools (onboard)

SFC, DISM (prüfen/reparieren), CHKDSK (nur lesend), Windows-Speicherdiagnose,
Datenträger-Gesundheit (SMART), Treiber-Inventar. Läufe starten nur auf Klick,
zeigen Live-Ausgabe, sind abbrechbar und werden zu einem Verdikt
(✓ / Hinweis / Problem) ausgewertet. Reparierende Tools sind gekennzeichnet.

## Updates

Einstellungen → Update-Feed-URL setzen. Feed-Format (JSON):

```json
{ "version": "1.1.0", "zip_url": "https://…/ca-1.1.0.zip", "sha256": "…", "notes": "…" }
```

„Nach Updates suchen" → Download wird SHA256-geprüft und nach `_staging/`
gelegt; der Launcher installiert es beim nächsten Start (mit Backup nach
`_backup/<version>/` und automatischem Rollback bei Fehlern). `config.json`
und die venv werden nie überschrieben.

## Grenzen

- Ein Freeze, der sich von selbst löst (ohne Neustart), hinterlässt keine
  Protokollspur.
- Ohne Administratorrechte keine Minidump-Auswertung und keine Admin-Prüftools.
- Die Ursachen-Klassifikation ist eine begründete Einschätzung mit ausgewiesener
  Konfidenz, kein Ersatz für eine Werkstatt-Diagnose bei Hardwaredefekten.

## Entwicklung

```
.venv\Scripts\python -m pytest          # 72 Tests (Engine, Parser, Updater, API)
.venv\Scripts\python -m src.app --no-window --port 8765   # Dev-Server
```

Struktur: `src/engine.py` (reine Analyse-Logik) · `src/collector.py` (Eventlog/
CIM via PowerShell) · `src/minidump.py` · `src/knowledge.py` + `src/kb/*.json`
(Wissensbasis, per Update aktualisierbar) · `src/tools/` (Prüftool-Registry/
Runner/Parser) · `src/updater.py` · `src/api.py` (FastAPI) · `src/web/`
(Frontend ohne Buildkette) · `launcher/run.ps1`.
