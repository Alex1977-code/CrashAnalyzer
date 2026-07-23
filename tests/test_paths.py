"""Pfad-Auflösung: Quell-Installation vs. eingefrorene EXE (PyInstaller)."""
import sys
from pathlib import Path

from src import paths, updater


def test_source_modus_nutzt_app_root():
    assert paths.is_frozen() is False
    assert paths.bundle_root() == updater.APP_ROOT
    assert paths.data_root() == updater.APP_ROOT


def test_frozen_modus_trennt_bundle_und_daten(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    assert paths.is_frozen() is True
    assert paths.bundle_root() == tmp_path / "bundle"
    data = paths.data_root()
    assert data == tmp_path / "appdata" / "CrashAnalyzer"
    assert data.is_dir(), "Datenverzeichnis wird angelegt"
