"""Führt Prüftools als Hintergrund-Subprozesse aus.

Ein Lauf je Tool gleichzeitig; Ausgabe wird als Byte-Puffer gesammelt und erst
beim Lesen dekodiert (sfc liefert UTF-16, chkdsk/DISM OEM-Codepage, PowerShell
UTF-8 — decode_output erkennt das).
"""
from __future__ import annotations

import base64
import subprocess
import threading
import uuid
from datetime import datetime, timezone


class ToolBusy(Exception):
    pass


def decode_output(buf: bytes) -> str:
    if not buf:
        return ""
    if b"\x00" in buf:
        try:
            return buf.decode("utf-16-le").replace("﻿", "")
        except UnicodeDecodeError:
            pass
    try:
        return buf.decode("utf-8")
    except UnicodeDecodeError:
        return buf.decode("cp850", errors="replace")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


class _Run:
    def __init__(self, tool, params):
        self.run_id = uuid.uuid4().hex[:12]
        self.tool = tool
        self.params = params or {}
        self.status = "running"
        self.started = _now()
        self.finished: str | None = None
        self.exit_code: int | None = None
        self.result: dict | None = None
        self.error: str | None = None
        self.buf = bytearray()
        self.proc: subprocess.Popen | None = None
        self.cancelled = False


class RunManager:
    def __init__(self):
        self._runs: dict[str, _Run] = {}
        self._lock = threading.Lock()

    # ---------- Lebenszyklus ----------

    def start(self, tool, params: dict | None = None) -> str:
        with self._lock:
            for r in self._runs.values():
                if r.tool.id == tool.id and r.status == "running":
                    raise ToolBusy(f"{tool.name} läuft bereits")
            run = _Run(tool, params)
            self._runs[run.run_id] = run

        argv = self._build_argv(tool, run.params)
        if tool.kind == "launch":
            self._start_launch(run, argv)
        else:
            t = threading.Thread(target=self._work, args=(run, argv), daemon=True)
            t.start()
        return run.run_id

    def _build_argv(self, tool, params: dict) -> list[str]:
        cmd = tool.command
        if callable(cmd):
            cmd = cmd(params)
        if tool.kind == "powershell":
            script = "$ProgressPreference = 'SilentlyContinue'\n" + str(cmd)
            encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
            return ["powershell.exe", "-NoProfile", "-NonInteractive",
                    "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded]
        return list(cmd)

    def _start_launch(self, run: _Run, argv: list[str]) -> None:
        try:
            subprocess.Popen(argv, creationflags=subprocess.CREATE_NEW_CONSOLE)
            run.exit_code = 0
            run.result = run.tool.parser("", 0)
            run.status = "done"
        except OSError as exc:
            run.error = str(exc)
            run.status = "failed"
        run.finished = _now()

    def _work(self, run: _Run, argv: list[str]) -> None:
        try:
            run.proc = subprocess.Popen(
                argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError as exc:
            run.error = f"Start fehlgeschlagen: {exc}"
            run.status = "failed"
            run.finished = _now()
            return
        assert run.proc.stdout is not None
        while True:
            chunk = run.proc.stdout.read(4096)
            if not chunk:
                break
            with self._lock:
                run.buf.extend(chunk)
        run.exit_code = run.proc.wait()
        if run.cancelled:
            run.status = "cancelled"
        else:
            try:
                run.result = run.tool.parser(decode_output(bytes(run.buf)), run.exit_code)
                run.status = "done"
            except Exception as exc:  # Parser darf den Lauf nicht "verlieren"
                run.error = f"Auswertung fehlgeschlagen: {exc}"
                run.status = "failed"
        run.finished = _now()

    def cancel(self, run_id: str) -> None:
        run = self._require(run_id)
        run.cancelled = True
        if run.proc and run.proc.poll() is None:
            run.proc.kill()

    # ---------- Abfragen ----------

    def _require(self, run_id: str) -> _Run:
        try:
            return self._runs[run_id]
        except KeyError:
            raise KeyError(f"Unbekannter Lauf: {run_id}") from None

    def get(self, run_id: str) -> dict:
        r = self._require(run_id)
        return {
            "run_id": r.run_id, "tool_id": r.tool.id, "status": r.status,
            "started": r.started, "finished": r.finished,
            "exit_code": r.exit_code, "result": r.result, "error": r.error,
        }

    def output_text(self, run_id: str) -> str:
        r = self._require(run_id)
        with self._lock:
            return decode_output(bytes(r.buf))

    def output_delta(self, run_id: str, offset: int) -> tuple[str, int]:
        text = self.output_text(run_id)
        offset = max(0, min(offset, len(text)))
        return text[offset:], len(text)

    def last_result(self, tool_id: str) -> dict | None:
        candidates = [r for r in self._runs.values()
                      if r.tool.id == tool_id and r.status in ("done", "failed", "cancelled")]
        if not candidates:
            return None
        return self.get(max(candidates, key=lambda r: r.started).run_id)

    def active_run(self, tool_id: str) -> str | None:
        for r in self._runs.values():
            if r.tool.id == tool_id and r.status == "running":
                return r.run_id
        return None
