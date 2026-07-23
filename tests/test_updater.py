"""Update-Mechanismus: Feed-Check, Download+Hash, Staging, Apply mit Rollback."""
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from src import updater


def make_app_root(tmp_path: Path, version="1.0.0") -> Path:
    root = tmp_path / "app"
    (root / "src").mkdir(parents=True)
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    (root / "src" / "engine.py").write_text("alt = True\n", encoding="utf-8")
    (root / "config.json").write_text('{"days": 14}', encoding="utf-8")
    return root


def make_feed(tmp_path: Path, version="1.1.0", zip_extra=None, break_hash=False,
              feed_extra=None) -> str:
    feed_dir = tmp_path / "feed"
    feed_dir.mkdir(exist_ok=True)
    zip_path = feed_dir / f"crash-analyzer-{version}.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("VERSION", version + "\n")
        z.writestr("src/engine.py", "neu = True\n")
        z.writestr("src/neu_dazu.py", "x = 1\n")
        for name, content in (zip_extra or {}).items():
            z.writestr(name, content)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if break_hash:
        digest = "0" * 64
    feed = {"version": version, "zip_url": zip_path.as_uri(),
            "sha256": digest, "notes": "Testrelease", **(feed_extra or {})}
    feed_path = feed_dir / "feed.json"
    feed_path.write_text(json.dumps(feed), encoding="utf-8")
    return feed_path.as_uri()


def test_check_reicht_exe_und_release_links_durch(tmp_path):
    root = make_app_root(tmp_path)
    url = make_feed(tmp_path, "1.1.0", feed_extra={
        "exe_url": "https://example.org/CrashAnalyzer.exe",
        "release_url": "https://example.org/releases/v1.1.0",
    })
    info = updater.check(url, root=str(root))
    assert info["exe_url"] == "https://example.org/CrashAnalyzer.exe"
    assert info["release_url"] == "https://example.org/releases/v1.1.0"


def test_check_erkennt_neue_version(tmp_path):
    root = make_app_root(tmp_path)
    url = make_feed(tmp_path, "1.1.0")
    info = updater.check(url, root=str(root))
    assert info["available"] is True
    assert info["latest"] == "1.1.0"
    assert info["current"] == "1.0.0"
    assert info["notes"] == "Testrelease"


def test_check_keine_neue_version(tmp_path):
    root = make_app_root(tmp_path, version="2.0.0")
    url = make_feed(tmp_path, "1.1.0")
    info = updater.check(url, root=str(root))
    assert info["available"] is False


def test_download_staged_mit_hashpruefung(tmp_path):
    root = make_app_root(tmp_path)
    url = make_feed(tmp_path, "1.1.0")
    staged = updater.download(url, root=str(root))
    assert staged == "1.1.0"
    manifest = json.loads((root / "_staging" / "manifest.json").read_text())
    assert manifest["version"] == "1.1.0"
    assert (root / "_staging" / "update.zip").exists()


def test_download_hash_mismatch_verwirft_staging(tmp_path):
    root = make_app_root(tmp_path)
    url = make_feed(tmp_path, "1.1.0", break_hash=True)
    with pytest.raises(updater.UpdateError):
        updater.download(url, root=str(root))
    assert not (root / "_staging" / "update.zip").exists()


def test_apply_ersetzt_dateien_und_schont_config(tmp_path):
    root = make_app_root(tmp_path)
    url = make_feed(tmp_path, "1.1.0")
    updater.download(url, root=str(root))
    applied, msg = updater.apply_staged(str(root))
    assert applied is True
    assert (root / "VERSION").read_text().strip() == "1.1.0"
    assert "neu" in (root / "src" / "engine.py").read_text()
    assert (root / "src" / "neu_dazu.py").exists()
    assert (root / "config.json").read_text() == '{"days": 14}', "config bleibt erhalten"
    assert not (root / "_staging" / "update.zip").exists(), "Staging geleert"
    assert (root / "_backup" / "1.0.0" / "VERSION").exists(), "Backup angelegt"


def test_apply_ohne_staging_tut_nichts(tmp_path):
    root = make_app_root(tmp_path)
    applied, msg = updater.apply_staged(str(root))
    assert applied is False


def test_apply_zip_slip_wird_abgelehnt_und_zurueckgerollt(tmp_path):
    root = make_app_root(tmp_path)
    url = make_feed(tmp_path, "1.1.0", zip_extra={"../boese.txt": "x"})
    updater.download(url, root=str(root))
    applied, msg = updater.apply_staged(str(root))
    assert applied is False
    assert (root / "VERSION").read_text().strip() == "1.0.0", "Rollback"
    assert not (tmp_path / "boese.txt").exists()
    assert not (root / "_staging" / "update.zip").exists(), "Staging trotzdem geleert"


def test_version_mit_utf8_bom_wird_sauber_gelesen(tmp_path):
    # PowerShell 5.1 (Set-Content -Encoding utf8) schreibt BOM
    (tmp_path / "VERSION").write_bytes(b"\xef\xbb\xbf1.0.0\r\n")
    assert updater.current_version(tmp_path) == "1.0.0"


def test_semver_vergleich():
    assert updater.is_newer("1.10.0", "1.9.9")
    assert not updater.is_newer("1.0.0", "1.0.0")
    assert not updater.is_newer("0.9.0", "1.0.0")
    assert updater.is_newer("2.0.0-beta", "1.9.0") is True  # Suffixe tolerieren
