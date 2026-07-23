"""Wissensbasis: Bugcheck-Codes, Empfehlungskatalog, Episoden-Art→Empfehlungen.

Die Daten liegen als JSON in src/kb/ und sind damit ohne Code-Änderung
über den Update-Mechanismus aktualisierbar.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

KB_DIR = Path(__file__).parent / "kb"

# Empfehlungen je Episoden-Art (wenn kein Bugcheck-Code die Auswahl treibt)
KIND_RECS: dict[str, list[str]] = {
    "power_loss": ["rec_cables_psu", "rec_temps", "rec_fastboot_off", "rec_professional"],
    "power_button": ["rec_temps", "rec_gpu_driver", "rec_driver_update", "rec_memtest"],
    "hardware": ["rec_temps", "rec_no_oc", "rec_bios_update", "rec_ram_reseat", "rec_professional"],
    "storage": ["rec_backup_now", "rec_chkdsk", "rec_disk_health", "rec_cables_psu"],
    "bsod": ["rec_windows_update", "rec_driver_update", "rec_sfc", "rec_memtest", "rec_professional"],
}

FALLBACK_RECS = ["rec_windows_update", "rec_driver_update", "rec_sfc", "rec_memtest", "rec_professional"]


@lru_cache(maxsize=1)
def all_bugchecks() -> dict[int, dict]:
    raw = json.loads((KB_DIR / "bugchecks.json").read_text(encoding="utf-8"))
    return {int(code): entry for code, entry in raw.items()}


@lru_cache(maxsize=1)
def recommendations() -> list[dict]:
    return json.loads((KB_DIR / "recommendations.json").read_text(encoding="utf-8"))


def recommendation_by_id(rec_id: str) -> dict | None:
    return next((r for r in recommendations() if r["id"] == rec_id), None)


def bugcheck_info(code: int) -> dict:
    entry = all_bugchecks().get(code)
    if entry is None:
        entry = {
            "name": "UNBEKANNTER_STOPCODE",
            "klartext": (
                "Für diesen Stopcode liegt keine spezifische Beschreibung vor. "
                "Es gelten die allgemeinen Schritte gegen Bluescreens: Updates, "
                "Treiber, Systemdateien und Arbeitsspeicher prüfen."
            ),
            "ursachen": ["Treiber", "Arbeitsspeicher", "Software-Konflikte"],
            "rec_ids": list(FALLBACK_RECS),
            "fallback": True,
        }
    else:
        entry = {**entry, "fallback": False}
    entry["hex"] = f"0x{code:08X}"
    return entry
