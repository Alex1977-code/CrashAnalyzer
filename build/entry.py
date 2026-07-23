"""PyInstaller-Einstiegspunkt der CrashAnalyzer.exe.

Im --windowed-Modus gibt es keine Konsole: sys.stdout/stderr sind None und
jedes print()/Logging würde crashen. Beide Streams werden deshalb in eine
Logdatei unter %LOCALAPPDATA%\\CrashAnalyzer umgeleitet.
"""
import os
import sys
from pathlib import Path


def _ensure_streams() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    base = Path(os.environ.get("LOCALAPPDATA", ".")) / "CrashAnalyzer"
    try:
        base.mkdir(parents=True, exist_ok=True)
        log = open(base / "app.log", "a", buffering=1, encoding="utf-8", errors="replace")
    except OSError:
        log = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log


_ensure_streams()

from src.app import main  # noqa: E402  (Streams müssen vorher stehen)

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        raise
