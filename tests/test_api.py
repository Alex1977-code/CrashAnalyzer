"""REST-API: Analyse, Konfiguration, Prüftool-Läufe, Update-Endpunkte."""
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.tools.registry import ToolDef
from tests.conftest import BASE, kernel_power_41, make_bundle
from tests.test_updater import make_feed


def echo_tool(needs_admin=False, tool_id="echo_test"):
    return ToolDef(
        id=tool_id, name="Echo", description="Test", needs_admin=needs_admin,
        repairs=False, duration_hint="1 s", kind="process",
        command=["cmd", "/c", "echo", "hallo-api"],
        parser=lambda out, code: {"verdict": "ok", "summary": "fertig", "details": None},
    )


def slow_tool():
    return ToolDef(
        id="slow_api", name="Slow", description="Test", needs_admin=False,
        repairs=False, duration_hint="5 s", kind="process",
        command=["ping", "-n", "8", "127.0.0.1"],
        parser=lambda out, code: {"verdict": "ok", "summary": "fertig", "details": None},
    )


@pytest.fixture
def app_env(tmp_path):
    calls = {"n": 0}

    def fake_collect(days):
        calls["n"] += 1
        return make_bundle([kernel_power_41(BASE)], days=days)

    (tmp_path / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    app = create_app(collect_fn=fake_collect, tools=[echo_tool(), echo_tool(True, "adm"), slow_tool()],
                     root=str(tmp_path), is_admin_fn=lambda: False)
    return TestClient(app), calls, tmp_path


def wait_status(client, run_id, timeout=15.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/api/tools/runs/{run_id}").json()
        if r["status"] != "running":
            return r
        time.sleep(0.05)
    raise AssertionError("Lauf nicht fertig")


def test_meta(app_env):
    client, _, _ = app_env
    m = client.get("/api/meta").json()
    assert m["version"] == "1.0.0"
    assert m["is_admin"] is False


def test_analysis_mit_cache_und_refresh(app_env):
    client, calls, _ = app_env
    a1 = client.get("/api/analysis").json()
    assert a1["summary"]["crash_count"] == 1
    assert calls["n"] == 1
    client.get("/api/analysis")
    assert calls["n"] == 1, "zweiter Aufruf kommt aus dem Cache"
    client.get("/api/analysis?refresh=1")
    assert calls["n"] == 2
    client.get("/api/analysis?days=7")
    assert calls["n"] == 3, "anderes Zeitfenster erzwingt Neuanalyse"


def test_config_roundtrip_und_validierung(app_env):
    client, _, _ = app_env
    cfg = client.get("/api/config").json()
    assert cfg["days"] == 30
    r = client.put("/api/config", json={"days": 60, "feed_url": ""})
    assert r.status_code == 200
    assert client.get("/api/config").json()["days"] == 60
    assert client.put("/api/config", json={"days": 0, "feed_url": ""}).status_code == 422
    assert client.put("/api/config",
                      json={"days": 30, "feed_url": "ftp://x"}).status_code == 422


def test_tools_liste_mit_verfuegbarkeit(app_env):
    client, _, _ = app_env
    tools = client.get("/api/tools").json()
    by_id = {t["id"]: t for t in tools}
    assert by_id["echo_test"]["available"] is True
    assert by_id["adm"]["available"] is False, "Admin-Tool ohne Adminrechte nicht verfügbar"
    assert by_id["adm"]["needs_admin"] is True


def test_tool_lauf_lebenszyklus(app_env):
    client, _, _ = app_env
    r = client.post("/api/tools/echo_test/start", json={})
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    done = wait_status(client, run_id)
    assert done["status"] == "done"
    assert done["result"]["verdict"] == "ok"
    out = client.get(f"/api/tools/runs/{run_id}", params={"offset": 0}).json()
    assert "hallo-api" in out["output_delta"]
    assert out["next_offset"] > 0


def test_tool_admin_erforderlich_403(app_env):
    client, _, _ = app_env
    assert client.post("/api/tools/adm/start", json={}).status_code == 403


def test_tool_doppelstart_409_und_cancel(app_env):
    client, _, _ = app_env
    run_id = client.post("/api/tools/slow_api/start", json={}).json()["run_id"]
    assert client.post("/api/tools/slow_api/start", json={}).status_code == 409
    assert client.post(f"/api/tools/runs/{run_id}/cancel").status_code == 200
    assert wait_status(client, run_id)["status"] == "cancelled"


def test_unbekanntes_tool_404(app_env):
    client, _, _ = app_env
    assert client.post("/api/tools/gibtsnicht/start", json={}).status_code == 404


def test_update_unkonfiguriert(app_env):
    client, _, _ = app_env
    s = client.get("/api/update/status").json()
    assert s["state"] == "unconfigured"
    assert client.post("/api/update/check").status_code == 400


def test_update_check_und_download_mit_feed(app_env, tmp_path):
    client, _, root = app_env
    url = make_feed(tmp_path, "1.1.0")
    client.put("/api/config", json={"days": 30, "feed_url": url})
    info = client.post("/api/update/check").json()
    assert info["available"] is True and info["latest"] == "1.1.0"
    r = client.post("/api/update/download").json()
    assert r["staged_version"] == "1.1.0"
    s = client.get("/api/update/status").json()
    assert s["state"] == "staged"
    assert s["staged_version"] == "1.1.0"
