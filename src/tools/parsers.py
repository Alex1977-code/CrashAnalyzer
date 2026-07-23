"""Wandelt Rohausgaben der Prüftools in ein Verdikt (ok/warning/problem/unknown)
mit deutscher Zusammenfassung um. Erkennt deutsche und englische Ausgaben."""
from __future__ import annotations

import json
from datetime import datetime


def _result(verdict: str, summary: str, details: str | None = None) -> dict:
    return {"verdict": verdict, "summary": summary, "details": details}


def _unknown(output: str) -> dict:
    tail = output.strip()[-800:] or None
    return _result("unknown", "Die Ausgabe konnte nicht eindeutig ausgewertet werden.", tail)


def parse_sfc(output: str, exit_code: int) -> dict:
    low = output.lower()
    if not low.strip():
        return _unknown(output)
    if "konnte einige davon jedoch nicht reparieren" in low or "unable to fix" in low:
        return _result(
            "problem",
            "SFC hat beschädigte Systemdateien gefunden, konnte aber nicht alle reparieren.",
            "Nächster Schritt: Windows-Abbild reparieren (DISM /RestoreHealth) ausführen "
            "und die SFC-Prüfung danach wiederholen.",
        )
    if "erfolgreich repariert" in low or "successfully repaired" in low:
        return _result(
            "warning",
            "SFC hat beschädigte Systemdateien gefunden und repariert.",
            "Die Reparatur war erfolgreich. Rechner neu starten und beobachten, "
            "ob die Probleme behoben sind.",
        )
    if "keine integritätsverletzungen" in low or "did not find any integrity violations" in low:
        return _result("ok", "Alle Systemdateien sind intakt — keine Beschädigungen gefunden.")
    return _unknown(output)


def parse_dism(output: str, exit_code: int) -> dict:
    low = output.lower()
    if not low.strip():
        return _unknown(output)
    if "nicht reparierbar" in low or "not repairable" in low:
        return _result(
            "problem",
            "Der Komponentenspeicher ist beschädigt und nicht automatisch reparierbar.",
            "Windows-Reparaturinstallation (In-Place-Upgrade) erwägen; wichtige Daten vorher sichern.",
        )
    if "reparierbar" in low or "repairable" in low:
        return _result(
            "warning",
            "Der Komponentenspeicher ist beschädigt, kann aber repariert werden.",
            "Als Nächstes das Prüftool \"Windows-Abbild reparieren\" (dism_restore) ausführen.",
        )
    if ("keine komponentenspeicherbeschädigung" in low
            or "no component store corruption" in low):
        return _result("ok", "Das Windows-Abbild ist intakt — keine Beschädigung erkannt.")
    if ("wiederherstellungsvorgang wurde erfolgreich" in low
            or "restore operation completed" in low):
        return _result("ok", "Die Reparatur des Windows-Abbilds wurde erfolgreich abgeschlossen.",
                       "Danach die Systemdateien-Prüfung (SFC) erneut ausführen.")
    if exit_code == 0 and ("erfolgreich" in low or "successfully" in low):
        return _result("ok", "DISM wurde erfolgreich abgeschlossen.")
    return _unknown(output)


def parse_chkdsk(output: str, exit_code: int) -> dict:
    low = output.lower()
    if not low.strip():
        return _unknown(output)
    problem_marker = ("/f" in low and ("korrigieren" in low or "fix" in low or "run chkdsk" in low)) \
        or "beschädigung" in low or "corruption" in low
    if problem_marker or exit_code not in (0,):
        return _result(
            "problem",
            "CHKDSK hat Fehler im Dateisystem gefunden.",
            "Reparatur: Eingabeaufforderung als Administrator öffnen und \"chkdsk C: /F\" "
            "ausführen (die Prüfung läuft dann beim nächsten Neustart). Vorher wichtige "
            "Daten sichern.",
        )
    if ("keine probleme" in low or "no further action is required" in low
            or "found no problems" in low):
        return _result("ok", "Das Dateisystem ist in Ordnung — keine Probleme gefunden.")
    return _unknown(output)


def _as_list(parsed) -> list:
    if parsed is None:
        return []
    return parsed if isinstance(parsed, list) else [parsed]


def _extract_json(text: str):
    """Findet das JSON-Dokument in verrauschter Ausgabe (CLIXML-Progress etc.)."""
    text = text.strip()
    if not text:
        return None
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "[{":
            try:
                value, _ = decoder.raw_decode(text, i)
            except json.JSONDecodeError:
                continue
            if isinstance(value, (list, dict)):
                return value
    return None


def parse_disk_health(output: str, exit_code: int) -> dict:
    disks = _as_list(_extract_json(output))
    if not disks:
        return _unknown(output)

    lines, bad, warn = [], [], []
    for d in disks:
        name = d.get("FriendlyName") or "Datenträger"
        status = d.get("HealthStatus") or "?"
        parts = [f"{d.get('MediaType') or '?'}", f"{d.get('SizeGB')} GB", f"Zustand: {status}"]
        if d.get("Wear") is not None:
            parts.append(f"Abnutzung {d['Wear']} %")
        if d.get("ReadErrorsTotal") is not None:
            parts.append(f"Lesefehler {d['ReadErrorsTotal']}")
        if d.get("Temperature"):
            parts.append(f"{d['Temperature']} °C")
        lines.append(f"• {name} ({', '.join(parts)})")
        if status not in ("Healthy", "OK"):
            bad.append(name)
        elif (d.get("Wear") or 0) >= 80 or (d.get("ReadErrorsTotal") or 0) > 100:
            warn.append(name)

    details = "\n".join(lines)
    if bad:
        return _result("problem",
                       f"Datenträger meldet Probleme: {', '.join(bad)}. Daten umgehend sichern!",
                       details)
    if warn:
        return _result("warning",
                       f"Datenträger zeigt Verschleiß/Fehler: {', '.join(warn)}. Beobachten und Backup aktuell halten.",
                       details)
    n = len(disks)
    return _result("ok", f"Alle {n} Datenträger melden einen guten Zustand." if n != 1
                   else "Der Datenträger meldet einen guten Zustand.", details)


def parse_driver_inventory(output: str, exit_code: int) -> dict:
    drivers = _as_list(_extract_json(output))
    if not drivers:
        return _unknown(output)
    lines = []
    for d in drivers:
        raw = d.get("DriverDate") or ""
        try:
            datum = datetime.strptime(raw[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
        except ValueError:
            datum = raw or "?"
        lines.append(f"• {datum}  {d.get('DeviceName') or '?'} — Version "
                     f"{d.get('DriverVersion') or '?'} ({d.get('Manufacturer') or '?'})")
    return _result(
        "ok",
        f"{len(drivers)} Treiber, die zuletzt geänderten zuerst. Begannen die Abstürze "
        f"nach einem dieser Daten, ist dieser Treiber ein Verdächtiger.",
        "\n".join(lines),
    )


def parse_memdiag_start(output: str, exit_code: int) -> dict:
    return _result(
        "ok",
        "Windows-Speicherdiagnose gestartet.",
        "Windows fragt jetzt, ob sofort neu gestartet werden soll. Der Speichertest läuft "
        "vor dem Windows-Start; das Ergebnis erscheint danach hier in der App auf der "
        "Diagnose-Seite (Abschnitt Speicherdiagnose).",
    )
