# Crash Analyzer Implementation Plan

> **For agentic workers:** Ausführung INLINE in derselben Session durch den Spec-Autor
> (autonome Session, kein Subagent-Handoff). Die Datenverträge unten sind verbindlich.
> TDD je Task, Commit je Task.

**Goal:** Windows-Desktop-App, die Abstürze analysiert, Ursachen deutsch erklärt, Prüftools onboard ausführt und sich selbst aktualisieren kann.

**Architecture:** FastAPI-Backend (uvicorn-Thread) + pywebview/WebView2-Fenster; reine Analyse-Engine über normalisierten Event-Dicts; Prüftool-Runner mit Polling; Staged-Update durch Launcher angewendet.

**Tech Stack:** Python 3.12 (venv), FastAPI 0.139, uvicorn 0.51, pywebview 6.2, pytest 9, httpx (Tests), PowerShell 5.1 (Collector-Queries), Vanilla-ES-Module-Frontend.

---

## Verbindliche Datenverträge

### Normalisiertes Event (collector → engine)
```json
{"time": "2026-07-20T12:14:05+02:00", "log": "System", "provider": "Microsoft-Windows-Kernel-Power",
 "id": 41, "level": 1, "data": {"BugcheckCode": "209", "PowerButtonTimestamp": "0"}}
```
`data` = EventData Name→String-Wert (roh, Parsing macht die Engine).

### Collector-Bundle
`collect(days) -> dict` mit Schlüsseln: `collected_at, days, is_admin, system{os_name, os_version, build, boot_time, ram_gb, manufacturer, model, is_laptop, hostname}, events[], app_events[], memdiag_events[], update_events[], minidumps[{path,size,mtime,bugcheck{code,p1..p4}|null,error?}], memory_dmp|null, limits[str]`.
Jede Quelle einzeln try/except → Ausfall landet als Satz in `limits`.

### Analyse-Ergebnis (engine.analyze(bundle) → dict)
```
summary{crash_count, app_crash_count, main_suspect|null, headline, stability}
episodes[{id, time, kind: bsod|power_button|hardware|storage|power_loss,
          title, what, why, confidence: hoch|mittel|niedrig, confidence_reason,
          bugcheck{code,hex,name,params[],source: event41|event1001|minidump}|null,
          evidence[{time,text,event_id,provider}], recommendations[rec_id], dump_path|null}]
patterns[{kind: cluster|same_code|after_update|time_of_day, text}]
recommendations[{id, title, text, priority 1-4, category: sofort|diagnose|hardware|profi,
                 tool_id|null, command|null}]   # aggregiert, dedupliziert, sortiert
app_crashes{total, groups[{app, count, kind: crash|hang, last_time, top_module|null}]}
memdiag{last_run|null, result|null}
limits[str]
```

### Engine-Konstanten
Anker-Dedupe ±300 s · Indizienfenster 24 h davor / 15 min danach · Disk-Cluster ≥3 · TDR ≥2 ·
Häufung ≥3 Episoden in 7 Tagen · Bugcheck-Quellen-Präzedenz: event1001 > minidump > event41.

### Prüftool-Modell (tools/)
`ToolDef(id, name, description, needs_admin, repairs, duration_hint, kind: process|powershell|launch)`
`ToolResult{verdict: ok|warning|problem|unknown, summary, details|null}`
`Run{run_id, tool_id, status: running|done|failed|cancelled, started, finished|null, output, exit_code|null, result|null}`
Tools: sfc, dism_scan, dism_restore, chkdsk (read-only, Param volume), memdiag_start (launch),
memdiag_results (aus Bundle), disk_health (PS), driver_inventory (PS). Ein Lauf je Tool gleichzeitig.

### API
```
GET  /api/meta                       {version, is_admin, hostname}
GET  /api/analysis?days=&refresh=    Analyse (Cache bis refresh=1)
GET  /api/config | PUT /api/config   {days, feed_url}
GET  /api/tools                      [{ToolDef + last_result + available}]
POST /api/tools/{id}/start           {params?} → {run_id} | 409 wenn läuft | 403 wenn Admin fehlt
GET  /api/tools/runs/{run_id}?offset=N  {status, output_delta, next_offset, result, exit_code}
POST /api/tools/runs/{run_id}/cancel
GET  /api/update/status              {current_version, feed_url|null, state: unconfigured|idle|staged, staged_version?}
POST /api/update/check | /api/update/download
GET  /                               web/index.html + Statics
```

### Update-Feed
`{"version":"1.1.0","zip_url":"…","sha256":"…","notes":"…"}` → Download `_staging/update.zip` +
`_staging/manifest.json`; Launcher: validiert Hash erneut, Backup `_backup/<version>/`, entpackt
über Programmdateien (ausgenommen: .venv, config.json, _staging, _backup, reports, .git), bei
Fehler Rollback, `_staging` immer leeren.

## Tasks (je: Tests zuerst → minimal implementieren → pytest grün → commit)

1. **kb/ + knowledge.py** — `kb/bugchecks.json` (~22 Codes: name, klartext, ursachen[], rec_ids[]),
   `kb/recommendations.json` (gestufter Katalog inkl. tool_id-Verweise). Tests: Laden, Lookup
   bekannt/unbekannt (Fallback-Kategorie nach Codebereich), jede rec_id in bugchecks existiert.
2. **engine.py** — Tests: Fixture-Builder (`ev(id, time, provider, **data)`), Fälle: BSOD-mit-1001,
   41-mit-BugcheckCode-ohne-1001, nacktes 41 (power_loss), PowerButtonTimestamp≠0, WHEA→hardware,
   Disk-Cluster→storage, 4101×2+0x116, stabiler Rechner (leere Episoden, headline korrekt),
   Muster same_code/cluster/after_update, App-Crash-Gruppierung, Empfehlungs-Aggregation.
3. **minidump.py** — Header PAGEDU64 (Offset 0x38 Code, 0x40 P1..0x58 P4, u64 LE) / PAGEDUMP
   (0x38 Code, dann 4×u32). Tests mit synthetisch gebauten Dateien inkl. Trunkiert/Garbage.
4. **collector.py** — PS-Skript-Erzeugung (FilterHashtable je Quelle), `ToXml()`-EventData-Extraktion,
   CIM-Systeminfo, Admin-Check, Minidump-Ordner. Unit: PS-Skript-Snapshot + JSON-Normalisierung
   (PS-Aufruf gemockt); Integration-Smoke live (0 Abstürze erwartet auf dieser Maschine).
5. **tools/** — registry+runner (Thread, Ring-Puffer, Cancel, Timeout) + Parser sfc/dism/chkdsk
   (deutsche+englische Ausgaben!) + PS-Tools disk_health/driver_inventory. Tests: Parser mit
   Beispielausgaben; Runner mit `cmd /c echo`-Prozess; Cancel.
6. **updater.py** — check (urllib gegen file://+http-Feed im Test), download+sha256, stage;
   `apply_staged()`-Logik als Funktion (vom Launcher via `python -m src.updater --apply` nutzbar)
   mit Backup/Rollback. Tests: Happy Path, Hash-Mismatch, Apply-Fehler→Rollback.
7. **api.py + app.py** — DI: Collector/Tools injizierbar; TestClient-Tests: analysis mit
   Fake-Bundle, tools-Lebenszyklus (echo-Tool), update unconfigured, config-Roundtrip, 403/409-Pfade.
8. **web/** — dataviz-Skill VOR Zeitleiste laden. Seiten Diagnose/Prüftools/Einstellungen,
   deutsch, Dark/Light (prefers-color-scheme), Polling-Konsole, Zustand „keine Abstürze".
   Verifikation über Browser-Pane gegen laufenden uvicorn (echte Maschine).
9. **Launcher** — `CrashAnalyzer.bat` → `launcher/run.ps1`: Admin?→Relaunch elevated (catch
   Abbruch→weiter), venv-Bootstrap (python -m venv + pip install -r requirements.txt bei Fehlen),
   `updater --apply` falls Staging valide, dann `python -m src.app`. requirements.txt einfrieren.
10. **E2E + Doku** — pytest gesamt grün; Live-Start; Browser-Pane: Dashboard echte Daten,
    driver_inventory-Lauf, Screenshots; README.md (Nutzung, Update-Feed, Grenzen); Commit.

## Test-Matrix Engine (Kurzreferenz)
| Fixture | erwartetes kind | confidence |
|---|---|---|
| 41 + 1001(0x133) + Dump | bsod | hoch |
| 41 (BugcheckCode=209=0xD1) | bsod | hoch |
| 41 (alles 0) | power_loss | niedrig |
| 41 (PowerButtonTimestamp≠0) | power_button | mittel |
| 41 + WHEA 18 davor | hardware | mittel |
| 6008 + disk 7×3 davor | storage | mittel |
| 41 + 4101×2 + 1001(0x116) | bsod (GPU-Text) | hoch |
| nur 6005/6006/1074 | keine Episode | — |
