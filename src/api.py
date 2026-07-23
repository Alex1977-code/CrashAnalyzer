"""REST-API der App. Alle Abhängigkeiten (Collector, Tools, Root) sind
injizierbar, damit die API ohne echte Maschine testbar ist."""
from __future__ import annotations

import threading
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from src import collector as collector_mod
from src import config as config_mod
from src import engine, updater
from src.tools import registry as registry_mod
from src.tools.runner import RunManager, ToolBusy

WEB_DIR = Path(__file__).resolve().parent / "web"


class ConfigIn(BaseModel):
    days: int
    feed_url: str = ""

    @field_validator("days")
    @classmethod
    def _days_range(cls, v: int) -> int:
        if not 1 <= v <= 365:
            raise ValueError("days muss zwischen 1 und 365 liegen")
        return v

    @field_validator("feed_url")
    @classmethod
    def _url_schema(cls, v: str) -> str:
        if v and not v.startswith(("http://", "https://", "file://")):
            raise ValueError("feed_url muss mit http(s):// oder file:// beginnen")
        return v


def create_app(collect_fn=None, tools=None, root=None,
               is_admin_fn=None, run_manager=None) -> FastAPI:
    collect_fn = collect_fn or (lambda days: collector_mod.collect(days))
    tools = tools if tools is not None else registry_mod.all_tools()
    root = Path(root) if root else updater.APP_ROOT
    is_admin_fn = is_admin_fn or collector_mod.is_admin
    mgr = run_manager or RunManager()
    tool_map = {t.id: t for t in tools}

    app = FastAPI(title="Crash Analyzer", docs_url=None, redoc_url=None)
    cache: dict = {"key": None, "result": None}
    cache_lock = threading.Lock()

    @app.middleware("http")
    async def no_store(request, call_next):
        # Selbst-updatende App: nach einem Update darf kein Browser/WebView2
        # veraltete Module aus dem HTTP-Cache laden.
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    # ---------- Meta / Analyse ----------

    @app.get("/api/meta")
    def meta():
        return {
            "app": "Crash Analyzer",
            "version": updater.current_version(root),
            "is_admin": bool(is_admin_fn()),
            "web": WEB_DIR.is_dir(),
        }

    @app.get("/api/analysis")
    def analysis(days: int | None = Query(default=None, ge=1, le=365),
                 refresh: int = 0):
        eff_days = days or config_mod.load_config(root)["days"]
        with cache_lock:
            if cache["result"] is not None and cache["key"] == eff_days and not refresh:
                return cache["result"]
            result = engine.analyze(collect_fn(eff_days))
            cache.update(key=eff_days, result=result)
            return result

    # ---------- Konfiguration ----------

    @app.get("/api/config")
    def get_config():
        cfg = config_mod.load_config(root)
        return {"days": cfg["days"], "feed_url": cfg["update"]["feed_url"]}

    @app.put("/api/config")
    def put_config(cfg_in: ConfigIn):
        cfg = config_mod.load_config(root)
        cfg["days"] = cfg_in.days
        cfg["update"]["feed_url"] = cfg_in.feed_url
        config_mod.save_config(root, cfg)
        return {"days": cfg["days"], "feed_url": cfg["update"]["feed_url"]}

    # ---------- Prüftools ----------

    def _tool_or_404(tool_id: str):
        tool = tool_map.get(tool_id)
        if tool is None:
            raise HTTPException(404, f"Unbekanntes Prüftool: {tool_id}")
        return tool

    @app.get("/api/tools")
    def list_tools():
        admin = bool(is_admin_fn())
        out = []
        for t in tools:
            out.append({
                "id": t.id, "name": t.name, "description": t.description,
                "needs_admin": t.needs_admin, "repairs": t.repairs,
                "duration_hint": t.duration_hint, "kind": t.kind,
                "warning": t.warning,
                "available": admin or not t.needs_admin,
                "active_run": mgr.active_run(t.id),
                "last_result": mgr.last_result(t.id),
            })
        return out

    @app.post("/api/tools/{tool_id}/start")
    def start_tool(tool_id: str, body: dict = Body(default={})):
        tool = _tool_or_404(tool_id)
        if tool.needs_admin and not is_admin_fn():
            raise HTTPException(
                403, "Dieses Prüftool benötigt Administratorrechte. "
                     "Bitte die App über 'Als Administrator neu starten' ausführen.")
        try:
            run_id = mgr.start(tool, (body or {}).get("params") or {})
        except ToolBusy as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"run_id": run_id}

    @app.get("/api/tools/runs/{run_id}")
    def run_status(run_id: str, offset: int = 0):
        try:
            run = mgr.get(run_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        delta, next_offset = mgr.output_delta(run_id, offset)
        return {**run, "output_delta": delta, "next_offset": next_offset}

    @app.post("/api/tools/runs/{run_id}/cancel")
    def cancel_run(run_id: str):
        try:
            mgr.cancel(run_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"ok": True}

    # ---------- Update ----------

    def _feed_url() -> str:
        return config_mod.load_config(root)["update"]["feed_url"]

    @app.get("/api/update/status")
    def update_status():
        feed = _feed_url()
        staged = updater.staged_version(root)
        return {
            "current_version": updater.current_version(root),
            "feed_url": feed or None,
            "state": "staged" if staged else ("idle" if feed else "unconfigured"),
            "staged_version": staged,
        }

    @app.post("/api/update/check")
    def update_check():
        feed = _feed_url()
        if not feed:
            raise HTTPException(400, "Kein Update-Feed konfiguriert (Einstellungen).")
        try:
            return updater.check(feed, root)
        except updater.UpdateError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.post("/api/update/download")
    def update_download():
        feed = _feed_url()
        if not feed:
            raise HTTPException(400, "Kein Update-Feed konfiguriert (Einstellungen).")
        try:
            version = updater.download(feed, root)
        except updater.UpdateError as exc:
            raise HTTPException(502, str(exc)) from exc
        return {"staged_version": version,
                "hint": "Das Update wird beim nächsten Start der App installiert."}

    # ---------- Frontend ----------

    if WEB_DIR.is_dir():
        @app.get("/")
        def index():
            return FileResponse(WEB_DIR / "index.html")

        app.mount("/", StaticFiles(directory=str(WEB_DIR)), name="web")

    return app
