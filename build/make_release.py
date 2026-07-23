"""Baut die Release-Artefakte:

  release/crash-analyzer-<version>.zip   Update-/Quellpaket (was der Updater einspielt)
  release/feed.json                      Update-Feed (kommt zusaetzlich ins Repo-Root)

Aufruf:  python build/make_release.py [--notes "Text"]
Die URLs zeigen auf die GitHub-Release-Assets von Alex1977-code/CrashAnalyzer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "Alex1977-code/CrashAnalyzer"

# Inhalt des Update-Pakets: genau das, was eine Quell-Installation ausmacht
INCLUDE_FILES = ["VERSION", "CrashAnalyzer.bat", "requirements.txt", "README.md", "LICENSE"]
INCLUDE_TREES = ["src", "launcher"]
EXCLUDE_DIR_NAMES = {"__pycache__"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_zip(version: str, out_dir: Path) -> Path:
    zip_path = out_dir / f"crash-analyzer-{version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in INCLUDE_FILES:
            p = ROOT / name
            if p.exists():
                z.write(p, name)
        for tree in INCLUDE_TREES:
            for p in sorted((ROOT / tree).rglob("*")):
                if p.is_dir() or any(part in EXCLUDE_DIR_NAMES for part in p.parts):
                    continue
                z.write(p, p.relative_to(ROOT).as_posix())
    return zip_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    out_dir = ROOT / "release"
    out_dir.mkdir(exist_ok=True)

    zip_path = build_zip(version, out_dir)
    feed = {
        "version": version,
        "zip_url": f"https://github.com/{REPO}/releases/download/v{version}/{zip_path.name}",
        "sha256": sha256(zip_path),
        "notes": args.notes,
        "exe_url": f"https://github.com/{REPO}/releases/download/v{version}/CrashAnalyzer.exe",
        "release_url": f"https://github.com/{REPO}/releases/tag/v{version}",
    }
    feed_path = out_dir / "feed.json"
    feed_path.write_text(json.dumps(feed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Version:  {version}")
    print(f"Zip:      {zip_path}  ({zip_path.stat().st_size / 1024:.0f} KB)")
    print(f"sha256:   {feed['sha256']}")
    print(f"Feed:     {feed_path}")
    exe = ROOT / "dist" / "CrashAnalyzer.exe"
    if exe.exists():
        print(f"EXE:      {exe}  ({exe.stat().st_size / 1024 / 1024:.1f} MB)")
        print(f"EXE-sha:  {sha256(exe)}")


if __name__ == "__main__":
    main()
