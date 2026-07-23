"""Selbst-Update: Feed prüfen, Paket laden (SHA256-verifiziert), stagen.

Das Anwenden übernimmt der Launcher VOR dem App-Start über
`python -m src.updater --apply` — so überschreibt sich nie ein laufender
Prozess. Bei Fehlern wird aus dem Backup zurückgerollt.

Feed-Format (JSON): {"version": "1.1.0", "zip_url": "...", "sha256": "...", "notes": "..."}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

APP_ROOT = Path(__file__).resolve().parent.parent
PROTECTED = {".venv", ".git", "_staging", "_backup", "reports", "config.json", "__pycache__"}
FETCH_TIMEOUT = 30


class UpdateError(Exception):
    pass


def is_newer(candidate: str, current: str) -> bool:
    def parse(v: str) -> tuple[int, ...]:
        parts = []
        for chunk in v.strip().split("."):
            digits = ""
            for ch in chunk:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            parts.append(int(digits or 0))
        return tuple(parts)
    return parse(candidate) > parse(current)


def current_version(root: str | Path = APP_ROOT) -> str:
    try:
        # utf-8-sig: toleriert BOM (z. B. von PowerShell 5.1 geschrieben)
        return (Path(root) / "VERSION").read_text(encoding="utf-8-sig").strip()
    except OSError:
        return "0.0.0"


def _fetch(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT) as resp:
            return resp.read()
    except Exception as exc:
        raise UpdateError(f"Abruf fehlgeschlagen ({url}): {exc}") from exc


def _load_feed(feed_url: str) -> dict:
    try:
        feed = json.loads(_fetch(feed_url).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise UpdateError(f"Update-Feed unlesbar: {exc}") from exc
    for key in ("version", "zip_url", "sha256"):
        if not feed.get(key):
            raise UpdateError(f"Update-Feed unvollständig: '{key}' fehlt")
    return feed


def check(feed_url: str, root: str | Path = APP_ROOT) -> dict:
    feed = _load_feed(feed_url)
    cur = current_version(root)
    return {
        "available": is_newer(feed["version"], cur),
        "latest": feed["version"],
        "current": cur,
        "notes": feed.get("notes") or "",
        "zip_url": feed["zip_url"],
        "exe_url": feed.get("exe_url"),
        "release_url": feed.get("release_url"),
    }


def _staging_dir(root: str | Path) -> Path:
    return Path(root) / "_staging"


def clear_staging(root: str | Path) -> None:
    shutil.rmtree(_staging_dir(root), ignore_errors=True)


def download(feed_url: str, root: str | Path = APP_ROOT) -> str:
    info = check(feed_url, root)
    if not info["available"]:
        raise UpdateError(f"Keine neuere Version verfügbar (aktuell: {info['current']}).")
    blob = _fetch(info["zip_url"])
    digest = hashlib.sha256(blob).hexdigest()
    feed_digest = _load_feed(feed_url)["sha256"].lower()
    if digest != feed_digest:
        clear_staging(root)
        raise UpdateError(
            "SHA256-Prüfsumme stimmt nicht — Download verworfen "
            f"(erwartet {feed_digest[:12]}…, erhalten {digest[:12]}…)."
        )
    staging = _staging_dir(root)
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "update.zip").write_bytes(blob)
    (staging / "manifest.json").write_text(
        json.dumps({"version": info["latest"], "sha256": digest}), encoding="utf-8")
    return info["latest"]


def _validate_zip(z: zipfile.ZipFile) -> str | None:
    for name in z.namelist():
        p = PurePosixPath(name.replace("\\", "/"))
        if p.is_absolute() or ".." in p.parts or (p.parts and p.parts[0].endswith(":")):
            return f"Unzulässiger Pfad im Update-Paket: {name!r}"
    return None


def _backup_app(root: Path, version: str) -> Path:
    target = root / "_backup" / version
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    for entry in root.iterdir():
        if entry.name in PROTECTED or entry.name == "config.json":
            continue
        if entry.is_dir():
            shutil.copytree(entry, target / entry.name,
                            ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(entry, target / entry.name)
    return target


def _restore_backup(root: Path, backup: Path) -> None:
    for entry in backup.iterdir():
        dest = root / entry.name
        if entry.is_dir():
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(entry, dest)
        else:
            shutil.copy2(entry, dest)


def apply_staged(root: str | Path = APP_ROOT) -> tuple[bool, str]:
    root = Path(root)
    staging = _staging_dir(root)
    zip_path = staging / "update.zip"
    manifest_path = staging / "manifest.json"
    if not (zip_path.exists() and manifest_path.exists()):
        clear_staging(root)
        return False, "Kein vorbereitetes Update vorhanden."

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        if digest != str(manifest.get("sha256", "")).lower():
            return False, "Staging beschädigt (Prüfsumme) — Update verworfen."

        with zipfile.ZipFile(zip_path) as z:
            problem = _validate_zip(z)
            if problem:
                return False, f"{problem} — Update verworfen."

            backup = _backup_app(root, current_version(root))
            try:
                for name in z.namelist():
                    parts = PurePosixPath(name.replace("\\", "/")).parts
                    if not parts or parts[0] in PROTECTED or name.endswith("/"):
                        continue
                    dest = root.joinpath(*parts)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(name) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
            except Exception as exc:
                _restore_backup(root, backup)
                return False, f"Update fehlgeschlagen, Rollback ausgeführt: {exc}"

        return True, f"Update auf Version {manifest.get('version')} installiert."
    except Exception as exc:
        return False, f"Update abgebrochen: {exc}"
    finally:
        clear_staging(root)


def staged_version(root: str | Path = APP_ROOT) -> str | None:
    manifest = _staging_dir(root) / "manifest.json"
    try:
        return json.loads(manifest.read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Crash Analyzer Updater")
    ap.add_argument("--apply", action="store_true", help="vorbereitetes Update anwenden")
    ap.add_argument("--root", default=str(APP_ROOT))
    args = ap.parse_args()
    if args.apply:
        applied, msg = apply_staged(args.root)
        print(msg)
        return 0 if applied else 1
    print(f"Aktuelle Version: {current_version(args.root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
