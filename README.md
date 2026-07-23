# Crash Analyzer

Windows-Desktop-App, die nach einem Absturz analysiert, **was** passiert ist,
**warum** (mit Konfidenz), und **was zu tun ist** — auf Deutsch, auch für
Nicht-Techniker. Diagnose-Prüftools sind direkt eingebaut, die App kann sich
selbst aktualisieren. Alle Daten bleiben auf dem Rechner.

## Download (Windows-EXE)

**⬇ [CrashAnalyzer.exe herunterladen](https://github.com/Alex1977-code/CrashAnalyzer/releases/latest/download/CrashAnalyzer.exe)** — keine Installation nötig, einfach starten.

- Für volle Funktion (Minidumps, SFC/DISM/CHKDSK) per Rechtsklick → **Als Administrator ausführen**.
- Die EXE ist nicht signiert: Windows SmartScreen kann warnen — „Weitere Informationen" →
  „Trotzdem ausführen". Die Prüfsumme (SHA256) steht in den [Release-Notes](https://github.com/Alex1977-code/CrashAnalyzer/releases/latest).
- Einstellungen werden unter `%LOCALAPPDATA%\CrashAnalyzer` gespeichert.

## Start aus dem Quellcode

Repo klonen und Doppelklick auf **`CrashAnalyzer.bat`**.

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

## Updates (aus diesem Repository)

Der Update-Feed ist ab Werk auf dieses Repo eingestellt
([`feed.json`](https://raw.githubusercontent.com/Alex1977-code/CrashAnalyzer/main/feed.json)).
Einstellungen → „Nach Updates suchen":

- **Quell-Installation:** Das Update-Zip wird SHA256-geprüft nach `_staging/`
  geladen; der Launcher installiert es beim nächsten Start (Backup nach
  `_backup/<version>/`, automatischer Rollback bei Fehlern). `config.json` und
  die venv werden nie überschrieben.
- **EXE:** Die App zeigt einen Download-Link auf die neue EXE (eine Onefile-EXE
  ersetzt sich nicht selbst).

Neues Release veröffentlichen: Version in `VERSION` erhöhen →
`python build/make_release.py` → GitHub-Release `v<version>` mit
`CrashAnalyzer.exe` + `crash-analyzer-<version>.zip` anlegen → das erzeugte
`release/feed.json` ins Repo-Root committen.

Feed-Format (JSON):

```json
{ "version": "1.1.0", "zip_url": "…", "sha256": "…", "notes": "…", "exe_url": "…", "release_url": "…" }
```

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
