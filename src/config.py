"""Laden/Speichern der App-Konfiguration (config.json im App-Stammverzeichnis)."""
from __future__ import annotations

import json
from pathlib import Path

DEFAULTS = {"days": 30, "update": {"feed_url": ""}}


def load_config(root: str | Path) -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))  # tiefe Kopie
    path = Path(root) / "config.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cfg
    if isinstance(loaded.get("days"), int):
        cfg["days"] = loaded["days"]
    upd = loaded.get("update") or {}
    if isinstance(upd.get("feed_url"), str):
        cfg["update"]["feed_url"] = upd["feed_url"]
    return cfg


def save_config(root: str | Path, cfg: dict) -> None:
    path = Path(root) / "config.json"
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
