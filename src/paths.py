"""Pfad-Auflösung für beide Vertriebsformen.

Quell-Installation: alles liegt im App-Ordner (Repo-Checkout).
EXE (PyInstaller onefile): der Code läuft aus dem temporären Bundle
(sys._MEIPASS, nur lesbar) — persistente Daten (config.json) wandern
nach %LOCALAPPDATA%\\CrashAnalyzer.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "CrashAnalyzer"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Wo Code + mitgelieferte Daten (web/, kb/, VERSION) liegen."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def data_root() -> Path:
    """Wo veränderliche Daten (config.json, Staging) liegen."""
    if is_frozen():
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        root = base / APP_DIR_NAME
        root.mkdir(parents=True, exist_ok=True)
        return root
    return bundle_root()
