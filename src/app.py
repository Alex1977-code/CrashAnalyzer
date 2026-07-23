"""Einstieg der Desktop-App: uvicorn im Hintergrund-Thread + WebView2-Fenster.

Modi:
  python -m src.app                  natives App-Fenster (pywebview/WebView2)
  python -m src.app --browser        Standardbrowser statt App-Fenster
  python -m src.app --no-window      nur Server (Entwicklung/Verifikation)
  python -m src.app --port 8765      fester Port statt automatischer Wahl
"""
from __future__ import annotations

import argparse
import socket
import threading
import time
import webbrowser

import uvicorn

from src.api import create_app


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(app, port: int) -> uvicorn.Server:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("Server-Start dauerte zu lange")
        if not thread.is_alive():
            raise RuntimeError("Server-Thread beendet — Port belegt?")
        time.sleep(0.05)
    return server


def open_window(url: str, server: uvicorn.Server) -> None:
    try:
        import webview
    except ImportError:
        print("pywebview nicht installiert — öffne Standardbrowser.")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        return
    webview.create_window(
        "Crash Analyzer", url,
        width=1360, height=900, min_size=(1024, 700),
    )
    webview.start()
    server.should_exit = True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Crash Analyzer")
    ap.add_argument("--port", type=int, default=0, help="fester Port (0 = automatisch)")
    ap.add_argument("--browser", action="store_true", help="Standardbrowser statt App-Fenster")
    ap.add_argument("--no-window", action="store_true", help="nur Server starten")
    args = ap.parse_args(argv)

    port = args.port or find_free_port()
    server = start_server(create_app(), port)
    url = f"http://127.0.0.1:{port}"
    print(f"Crash Analyzer läuft auf {url}")

    if args.no_window:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    elif args.browser:
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    else:
        open_window(url, server)
    server.should_exit = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
