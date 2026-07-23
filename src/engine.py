"""Analyse-Engine: bildet aus normalisierten Events Absturz-Episoden,
klassifiziert Ursachen, erkennt Muster und aggregiert Empfehlungen.

Reine Funktionen ohne I/O — Eingabe ist das Collector-Bundle (dict),
Ausgabe das Analyse-Ergebnis (dict) laut Datenvertrag im Plan.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta

from src import knowledge

ANCHOR_DEDUPE = timedelta(seconds=300)
EVIDENCE_BEFORE = timedelta(hours=24)
EVIDENCE_AFTER = timedelta(minutes=15)
BUGCHECK_MATCH_BEFORE = timedelta(minutes=10)
BUGCHECK_MATCH_AFTER = timedelta(minutes=30)
DISK_CLUSTER_MIN = 3
CLUSTER_WINDOW = timedelta(days=7)
CLUSTER_MIN = 3
UPDATE_CORRELATION = timedelta(days=14)

DISK_PROVIDER_ROOTS = ("disk", "ntfs", "volmgr", "volsnap", "storahci", "stornvme", "storport", "iastor")

KIND_LABELS = {
    "bsod": "Bluescreens",
    "power_loss": "Plötzlicher Stromverlust",
    "power_button": "Manuelles Ausschalten (Power-Taste)",
    "hardware": "Hardwarefehler",
    "storage": "Datenträgerprobleme",
}

SOURCE_LABELS = {
    "event1001": "Bluescreen-Protokoll",
    "minidump": "Absturz-Speicherabbild",
    "event41": "Kernel-Power-Protokoll",
}


def _t(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def _parse_int(value: str | None) -> int:
    if not value:
        return 0
    try:
        return int(str(value), 0)
    except ValueError:
        return 0


def _is_kernel_power_41(e: dict) -> bool:
    return e["id"] == 41 and "Kernel-Power" in e["provider"]


def _is_bugcheck_1001(e: dict) -> bool:
    return e["id"] == 1001 and (
        "SystemErrorReporting" in e["provider"] or "BugCheck" in e["provider"]
    )


def _is_disk_event(e: dict) -> bool:
    p = e["provider"].lower()
    return any(p.startswith(root) or root in p for root in DISK_PROVIDER_ROOTS) and e["id"] != 1001


def _is_whea(e: dict) -> bool:
    return "WHEA-Logger" in e["provider"]


def _is_tdr(e: dict) -> bool:
    return e["id"] == 4101


def _evidence_text(e: dict) -> str | None:
    if _is_whea(e):
        return f"Hardware-Fehler gemeldet (WHEA, Ereignis {e['id']})"
    if _is_tdr(e):
        return "Grafiktreiber hat nicht mehr reagiert und wurde zurückgesetzt (TDR)"
    if _is_disk_event(e):
        return f"Datenträgerfehler ({e['provider']}, Ereignis {e['id']})"
    if _is_bugcheck_1001(e):
        return "Bluescreen-Protokoll vorhanden (BugCheck 1001)"
    if e["id"] in (7031, 7034) and "Service Control" in e["provider"]:
        return "Ein Windows-Dienst wurde unerwartet beendet"
    return None


def _parse_1001(e: dict) -> tuple[dict | None, str | None]:
    """Liefert (bugcheck, dump_path) aus einem BugCheck-1001-Event."""
    text = e["data"].get("param1", "")
    m = re.search(r"0x([0-9a-fA-F]{8})\s*(?:\(([^)]*)\))?", text)
    if not m:
        return None, e["data"].get("param2") or None
    code = int(m.group(1), 16)
    params = [p.strip() for p in (m.group(2) or "").split(",") if p.strip()]
    return {"code": code, "params": params}, e["data"].get("param2") or None


class _Episode:
    def __init__(self, anchor: dict):
        self.anchor = anchor
        self.time = _t(anchor["time"])
        self.bugcheck_code = 0
        self.bugcheck_params: list[str] = []
        self.bugcheck_source: str | None = None
        self.power_button = False
        self.dump_path: str | None = None
        self.evidence: list[dict] = []
        self._absorb_anchor(anchor)

    def _absorb_anchor(self, anchor: dict) -> None:
        if _is_kernel_power_41(anchor):
            code = _parse_int(anchor["data"].get("BugcheckCode"))
            if code and not self.bugcheck_code:
                self.bugcheck_code = code
                self.bugcheck_params = [
                    anchor["data"].get(f"BugcheckParameter{i}", "0x0") for i in range(1, 5)
                ]
                self.bugcheck_source = "event41"
            if _parse_int(anchor["data"].get("PowerButtonTimestamp")):
                self.power_button = True

    def try_merge_anchor(self, anchor: dict) -> bool:
        if abs(_t(anchor["time"]) - self.time) > ANCHOR_DEDUPE:
            return False
        # 41 ist die reichere Quelle als 6008 — Daten übernehmen
        self._absorb_anchor(anchor)
        return True

    def apply_1001(self, e: dict) -> None:
        bug, dump = _parse_1001(e)
        if bug:
            self.bugcheck_code = bug["code"]
            self.bugcheck_params = bug["params"]
            self.bugcheck_source = "event1001"
        if dump and not self.dump_path:
            self.dump_path = dump

    def apply_minidump(self, dump: dict) -> None:
        if self.bugcheck_source != "event1001" and dump.get("bugcheck"):
            bc = dump["bugcheck"]
            self.bugcheck_code = bc["code"]
            self.bugcheck_params = [bc.get(f"p{i}", "0x0") for i in range(1, 5)]
            self.bugcheck_source = "minidump"
        if not self.dump_path:
            self.dump_path = dump["path"]


def _build_episodes(bundle: dict) -> list[_Episode]:
    events = sorted(bundle["events"], key=lambda e: e["time"])
    episodes: list[_Episode] = []
    for e in events:
        if not (_is_kernel_power_41(e) or e["id"] == 6008):
            continue
        if episodes and episodes[-1].try_merge_anchor(e):
            continue
        episodes.append(_Episode(e))

    for e in events:
        if not _is_bugcheck_1001(e):
            continue
        et = _t(e["time"])
        for epi in episodes:
            if epi.time - BUGCHECK_MATCH_BEFORE <= et <= epi.time + BUGCHECK_MATCH_AFTER:
                epi.apply_1001(e)
                break

    for dump in bundle.get("minidumps", []):
        try:
            mt = _t(dump["mtime"])
        except (KeyError, ValueError):
            continue
        for epi in episodes:
            if epi.time - BUGCHECK_MATCH_BEFORE <= mt <= epi.time + BUGCHECK_MATCH_AFTER:
                epi.apply_minidump(dump)
                break

    for epi in episodes:
        lo, hi = epi.time - EVIDENCE_BEFORE, epi.time + EVIDENCE_AFTER
        for e in events:
            if e is epi.anchor:
                continue
            if not (lo <= _t(e["time"]) <= hi):
                continue
            text = _evidence_text(e)
            if text:
                epi.evidence.append({
                    "time": e["time"], "text": text,
                    "event_id": e["id"], "provider": e["provider"],
                })
        epi.evidence.sort(key=lambda x: x["time"])
    return episodes


def _classify(epi: _Episode, is_laptop: bool) -> dict:
    whea = sum(1 for ev_ in epi.evidence if "WHEA" in ev_["text"])
    disk = sum(1 for ev_ in epi.evidence if "Datenträgerfehler" in ev_["text"])
    bugcheck = None

    if epi.bugcheck_code:
        kind = "bsod"
        info = knowledge.bugcheck_info(epi.bugcheck_code)
        bugcheck = {
            "code": epi.bugcheck_code, "hex": info["hex"], "name": info["name"],
            "params": epi.bugcheck_params, "source": epi.bugcheck_source,
        }
        title = f"Bluescreen ({info['name']})"
        what = ("Windows hat einen schweren Fehler festgestellt und den Rechner mit "
                "einem Bluescreen neu gestartet.")
        if epi.dump_path:
            what += " Ein Speicherabbild wurde gespeichert."
        why = info["klartext"]
        confidence, reason = "hoch", (
            f"Der Stopcode wurde eindeutig protokolliert (Quelle: {SOURCE_LABELS[epi.bugcheck_source]})."
        )
        recs = list(info["rec_ids"])
    elif epi.power_button:
        kind = "power_button"
        title = "Hart ausgeschaltet (Power-Taste)"
        what = ("Der Rechner wurde über die Power-Taste hart ausgeschaltet "
                "(Taste lange gedrückt).")
        why = ("In den meisten Fällen war der Rechner zuvor eingefroren und hat nicht mehr "
               "reagiert. Häufige Auslöser sind Grafiktreiber-Probleme, Überhitzung oder "
               "defekter Arbeitsspeicher.")
        confidence, reason = "mittel", (
            "Das harte Ausschalten ist protokolliert; der Grund für das vorherige "
            "Einfrieren lässt sich aus den Logs nur eingrenzen."
        )
        recs = list(knowledge.KIND_RECS["power_button"])
    elif whea:
        kind = "hardware"
        title = "Absturz mit Hardware-Fehlermeldungen"
        what = "Der Rechner ist ohne sauberes Herunterfahren ausgefallen."
        why = ("Kurz vor dem Ausfall wurden Hardware-Fehler (WHEA) protokolliert. Das deutet "
               "auf ein Problem mit CPU, Mainboard, Arbeitsspeicher oder Spannungsversorgung "
               "hin — auch Überhitzung oder instabile Übertaktung kommen infrage.")
        confidence, reason = "mittel", "Hardware-Fehlermeldungen im Vorfeld sind ein starkes Indiz."
        recs = list(knowledge.KIND_RECS["hardware"])
    elif disk >= DISK_CLUSTER_MIN:
        kind = "storage"
        title = "Absturz mit Datenträger-Fehlern"
        what = "Der Rechner ist ohne sauberes Herunterfahren ausgefallen."
        why = ("Vor dem Absturz häuften sich Datenträgerfehler. Festplatte/SSD, deren "
               "Verkabelung oder der Speichercontroller sind die Hauptverdächtigen. "
               "Wichtige Daten sollten umgehend gesichert werden.")
        confidence, reason = "mittel", f"{disk} Datenträgerfehler in den 24 Stunden vor dem Absturz."
        recs = list(knowledge.KIND_RECS["storage"])
    else:
        kind = "power_loss"
        title = "Plötzlicher Stromverlust"
        what = ("Der Rechner hat schlagartig den Strom verloren — es wurde weder ein "
                "Bluescreen noch ein Herunterfahren protokolliert.")
        why = ("Typische Ursachen: Stromausfall oder lockerer Stecker, ein schwächelndes "
               "Netzteil unter Last oder eine Überhitzungs-Notabschaltung.")
        if is_laptop:
            why += " Bei Laptops kommen zusätzlich Akku oder Netzteil infrage."
        confidence, reason = "niedrig", (
            "Windows konnte keinen Grund mehr protokollieren; die Ursache liegt "
            "unmittelbar vor dem Stromverlust."
        )
        recs = list(knowledge.KIND_RECS["power_loss"])

    if is_laptop and kind in ("power_loss", "power_button", "hardware"):
        if "rec_battery" not in recs:
            recs.append("rec_battery")

    return {
        "id": f"ep-{epi.time:%Y%m%d-%H%M%S}",
        "time": epi.anchor["time"],
        "kind": kind,
        "title": title,
        "what": what,
        "why": why,
        "confidence": confidence,
        "confidence_reason": reason,
        "bugcheck": bugcheck,
        "evidence": epi.evidence,
        "recommendations": recs,
        "dump_path": epi.dump_path,
    }


def _find_patterns(episodes: list[dict], update_events: list[dict]) -> list[dict]:
    patterns: list[dict] = []
    times = sorted(_t(e["time"]) for e in episodes)

    # Häufung: >= CLUSTER_MIN Episoden in 7 Tagen
    best = 0
    for i in range(len(times)):
        n = sum(1 for t2 in times if timedelta(0) <= t2 - times[i] <= CLUSTER_WINDOW)
        best = max(best, n)
    if best >= CLUSTER_MIN:
        patterns.append({
            "kind": "cluster",
            "text": f"{best} Abstürze innerhalb von 7 Tagen — der Rechner ist akut instabil, "
                    f"die Ursache ist aktiv.",
        })

    # Gleicher Stopcode mehrfach
    codes = Counter(e["bugcheck"]["name"] for e in episodes if e["bugcheck"])
    for name, n in codes.items():
        if n >= 2:
            patterns.append({
                "kind": "same_code",
                "text": f"Der Stopcode {name} trat {n}-mal auf — das spricht für eine "
                        f"konkrete, wiederkehrende Ursache statt Zufall.",
            })

    # Beginn nach Windows-Update
    if episodes and update_events:
        first_crash = min(times)
        candidates = []
        for u in update_events:
            ut = _t(u["time"])
            if timedelta(0) <= first_crash - ut <= UPDATE_CORRELATION:
                candidates.append(u)
        if candidates:
            last = max(candidates, key=lambda u: u["time"])
            kb = re.search(r"KB\d{6,}", last.get("message", "") or "")
            kb_txt = f" ({kb.group(0)})" if kb else ""
            patterns.append({
                "kind": "after_update",
                "text": f"Die Abstürze begannen kurz nach einer Update-Installation"
                        f"{kb_txt} am {_t(last['time']):%d.%m.%Y}. Ein Zusammenhang ist "
                        f"möglich — kürzlich aktualisierte Treiber/Updates prüfen.",
            })

    # Immer ähnliche Uhrzeit
    if len(times) >= 3:
        hours = Counter(t.hour for t in times)
        top_hour, n = hours.most_common(1)[0]
        if n >= 3:
            patterns.append({
                "kind": "time_of_day",
                "text": f"{n} Abstürze jeweils gegen {top_hour:02d} Uhr — das kann auf "
                        f"geplante Aufgaben (Backups, Updates) oder Lastspitzen hindeuten.",
            })
    return patterns


def _aggregate_recommendations(episodes: list[dict]) -> list[dict]:
    seen: list[str] = []
    for epi in episodes:
        for rid in epi["recommendations"]:
            if rid not in seen:
                seen.append(rid)
    resolved = [r for rid in seen if (r := knowledge.recommendation_by_id(rid))]
    return sorted(resolved, key=lambda r: r["priority"])


def _group_app_crashes(app_events: list[dict]) -> dict:
    groups: dict[tuple[str, str], dict] = {}
    for e in app_events:
        data = e["data"]
        # Win11 benennt die Felder (AppName/ModuleName), ältere Windows nur param1..N
        app = data.get("AppName") or data.get("param1") or "unbekannt"
        module = data.get("ModuleName") or data.get("param4")
        kind = "hang" if e["id"] == 1002 else "crash"
        g = groups.setdefault((app, kind), {
            "app": app, "kind": kind, "count": 0, "last_time": e["time"], "modules": Counter(),
        })
        g["count"] += 1
        g["last_time"] = max(g["last_time"], e["time"])
        if kind == "crash" and module:
            g["modules"][module] += 1
    out = []
    for g in groups.values():
        modules = g.pop("modules")
        g["top_module"] = modules.most_common(1)[0][0] if modules else None
        out.append(g)
    out.sort(key=lambda g: (-g["count"], g["app"]))
    return {"total": len(app_events), "groups": out}


def _memdiag(memdiag_events: list[dict]) -> dict:
    if not memdiag_events:
        return {"last_run": None, "result": None}
    last = max(memdiag_events, key=lambda e: e["time"])
    msg = (last.get("message") or "").strip()
    result = msg.splitlines()[0] if msg else "Ergebnis protokolliert (Details im Ereignisprotokoll)"
    return {"last_run": last["time"], "result": result}


def _main_suspect(episodes: list[dict]) -> str | None:
    if not episodes:
        return None
    kinds = Counter(e["kind"] for e in episodes)
    top_kind, _ = kinds.most_common(1)[0]
    if top_kind == "bsod":
        names = Counter(e["bugcheck"]["name"] for e in episodes if e["bugcheck"])
        name, n = names.most_common(1)[0]
        return f"Bluescreen ({name})" if n == 1 else f"Bluescreens ({name}, {n}×)"
    return KIND_LABELS[top_kind]


def analyze(bundle: dict) -> dict:
    is_laptop = bool(bundle.get("system", {}).get("is_laptop"))
    episodes = [_classify(epi, is_laptop) for epi in _build_episodes(bundle)]
    episodes.sort(key=lambda e: e["time"], reverse=True)

    patterns = _find_patterns(episodes, bundle.get("update_events", []))
    days = bundle.get("days", 30)
    n = len(episodes)
    suspect = _main_suspect(episodes)

    if n == 0:
        stability = "stabil"
        headline = f"Keine Systemabstürze in den letzten {days} Tagen gefunden."
    else:
        stability = "kritisch" if any(p["kind"] == "cluster" for p in patterns) else "instabil"
        word = "Systemabsturz" if n == 1 else "Systemabstürze"
        headline = f"{n} {word} in den letzten {days} Tagen — Hauptverdacht: {suspect}."

    app_crashes = _group_app_crashes(bundle.get("app_events", []))

    return {
        "generated_at": bundle.get("collected_at"),
        "days": days,
        "summary": {
            "crash_count": n,
            "app_crash_count": app_crashes["total"],
            "main_suspect": suspect,
            "headline": headline,
            "stability": stability,
        },
        "episodes": episodes,
        "patterns": patterns,
        "recommendations": _aggregate_recommendations(episodes),
        "app_crashes": app_crashes,
        "memdiag": _memdiag(bundle.get("memdiag_events", [])),
        "limits": list(bundle.get("limits", [])),
        "system": bundle.get("system", {}),
        "is_admin": bundle.get("is_admin"),
    }
