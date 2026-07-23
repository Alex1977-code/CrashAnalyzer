"""Prüftools: Registry, Ausgabe-Parser, Hintergrund-Runner."""
import json
import time

import pytest

from src.tools import parsers, registry
from src.tools.runner import RunManager, ToolBusy


# ---------- Registry ----------

def test_registry_vollstaendig():
    ids = [t.id for t in registry.all_tools()]
    assert len(ids) == len(set(ids))
    for erwartet in ("sfc", "dism_scan", "dism_restore", "chkdsk",
                     "memdiag_start", "disk_health", "driver_inventory"):
        assert erwartet in ids
    for t in registry.all_tools():
        assert t.name and t.description and t.duration_hint
        assert t.kind in ("process", "powershell", "launch")


def test_reparierende_tools_gekennzeichnet():
    assert registry.get_tool("dism_restore").repairs is True
    assert registry.get_tool("sfc").repairs is True
    assert registry.get_tool("disk_health").repairs is False


# ---------- Parser ----------

def test_sfc_ok_deutsch_und_englisch():
    de = "Überprüfung 100 % abgeschlossen.\r\nDer Windows-Ressourcenschutz hat keine Integritätsverletzungen gefunden."
    en = "Verification 100% complete.\r\nWindows Resource Protection did not find any integrity violations."
    assert parsers.parse_sfc(de, 0)["verdict"] == "ok"
    assert parsers.parse_sfc(en, 0)["verdict"] == "ok"


def test_sfc_repariert_ist_warnung():
    out = ("Der Windows-Ressourcenschutz hat beschädigte Dateien gefunden und "
           "erfolgreich repariert.")
    r = parsers.parse_sfc(out, 0)
    assert r["verdict"] == "warning"
    assert "repariert" in r["summary"]


def test_sfc_nicht_reparierbar_ist_problem():
    out = ("Der Windows-Ressourcenschutz hat beschädigte Dateien gefunden, konnte "
           "einige davon jedoch nicht reparieren.")
    assert parsers.parse_sfc(out, 0)["verdict"] == "problem"


def test_dism_scan_ok_und_reparierbar():
    ok = "Es wurde keine Komponentenspeicherbeschädigung erkannt.\r\nDer Vorgang wurde erfolgreich beendet."
    rep = "Die Komponentenspeicherbeschädigung ist reparierbar.\r\nDer Vorgang wurde erfolgreich beendet."
    assert parsers.parse_dism(ok, 0)["verdict"] == "ok"
    r = parsers.parse_dism(rep, 0)
    assert r["verdict"] == "warning"
    assert "dism_restore" in r["details"] or "reparieren" in r["summary"].lower()


def test_chkdsk_ok_und_problem():
    ok = "Der Typ des Dateisystems ist NTFS.\r\nEs wurden keine Probleme gefunden.\r\n"
    bad = ("Der Typ des Dateisystems ist NTFS.\r\n"
           "Beschädigungen im Volumebitmap gefunden.\r\n"
           "Führen Sie CHKDSK mit der /F-Option aus, um diese Probleme zu korrigieren.")
    assert parsers.parse_chkdsk(ok, 0)["verdict"] == "ok"
    r = parsers.parse_chkdsk(bad, 3)
    assert r["verdict"] == "problem"
    assert "/F" in r["details"] or "chkdsk" in r["summary"].lower()


def test_disk_health_json_gesund_und_defekt():
    healthy = json.dumps([{"FriendlyName": "Samsung SSD 990", "MediaType": "SSD",
                           "HealthStatus": "Healthy", "OperationalStatus": "OK",
                           "SizeGB": 931.5, "Wear": 4, "ReadErrorsTotal": 0,
                           "Temperature": 38}])
    sick = json.dumps([{"FriendlyName": "WDC HDD", "MediaType": "HDD",
                        "HealthStatus": "Warning", "OperationalStatus": "OK",
                        "SizeGB": 1863.0, "Wear": None, "ReadErrorsTotal": 512,
                        "Temperature": None}])
    r_ok = parsers.parse_disk_health(healthy, 0)
    assert r_ok["verdict"] == "ok"
    assert "Samsung" in r_ok["details"]
    r_bad = parsers.parse_disk_health(sick, 0)
    assert r_bad["verdict"] == "problem"
    assert "WDC" in r_bad["summary"] or "WDC" in r_bad["details"]


def test_driver_inventory_formatiert():
    data = json.dumps([
        {"DeviceName": "NVIDIA GeForce RTX 4080", "DriverVersion": "32.0.15.6109",
         "DriverDate": "2026-06-20", "Manufacturer": "NVIDIA"},
        {"DeviceName": "Intel(R) Ethernet", "DriverVersion": "12.19.2.60",
         "DriverDate": "2026-05-01", "Manufacturer": "Intel"},
    ])
    r = parsers.parse_driver_inventory(data, 0)
    assert r["verdict"] == "ok"
    assert "NVIDIA" in r["details"]
    assert "20.06.2026" in r["details"]


def test_parser_fallback_bei_leerer_ausgabe():
    r = parsers.parse_sfc("", 1)
    assert r["verdict"] == "unknown"


def test_disk_health_json_in_clixml_rauschen():
    # PowerShell 5.1 mischt CLIXML-Progress-Records in die Ausgabe
    noise = ('<Objs Version="1.1.0.1"><Obj S="progress"><AV>Module werden '
             'vorbereitet.</AV></Obj></Objs>')
    payload = json.dumps([{"FriendlyName": "SSD X", "MediaType": "SSD",
                           "HealthStatus": "Healthy", "OperationalStatus": "OK",
                           "SizeGB": 500.0, "Wear": 1, "ReadErrorsTotal": 0,
                           "Temperature": None}])
    r = parsers.parse_disk_health(payload + "\r\n" + noise, 0)
    assert r["verdict"] == "ok"
    r2 = parsers.parse_disk_health(noise + "\r\n" + payload, 0)
    assert r2["verdict"] == "ok"


def test_powershell_tools_unterdruecken_progress():
    import base64
    mgr = RunManager()
    argv = mgr._build_argv(registry.get_tool("disk_health"), {})
    script = base64.b64decode(argv[-1]).decode("utf-16-le")
    assert "$ProgressPreference" in script


# ---------- Runner ----------

def echo_tool():
    return registry.ToolDef(
        id="echo_test", name="Echo", description="Test", needs_admin=False,
        repairs=False, duration_hint="1 s", kind="process",
        command=["cmd", "/c", "echo", "hallo-welt"],
        parser=lambda out, code: {"verdict": "ok", "summary": f"exit={code}", "details": None},
    )


def slow_tool():
    return registry.ToolDef(
        id="slow_test", name="Slow", description="Test", needs_admin=False,
        repairs=False, duration_hint="3 s", kind="process",
        command=["ping", "-n", "10", "127.0.0.1"],
        parser=lambda out, code: {"verdict": "ok", "summary": "fertig", "details": None},
    )


def wait_done(mgr, run_id, timeout=15.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        run = mgr.get(run_id)
        if run["status"] not in ("running",):
            return run
        time.sleep(0.05)
    raise AssertionError("Run wurde nicht fertig")


def test_runner_fuehrt_prozess_aus_und_parst():
    mgr = RunManager()
    run_id = mgr.start(echo_tool(), {})
    run = wait_done(mgr, run_id)
    assert run["status"] == "done"
    assert run["exit_code"] == 0
    assert "hallo-welt" in mgr.output_text(run_id)
    assert run["result"]["summary"] == "exit=0"


def test_runner_output_delta_mit_offset():
    mgr = RunManager()
    run_id = mgr.start(echo_tool(), {})
    wait_done(mgr, run_id)
    full = mgr.output_text(run_id)
    delta, next_off = mgr.output_delta(run_id, 0)
    assert delta == full and next_off == len(full)
    delta2, _ = mgr.output_delta(run_id, next_off)
    assert delta2 == ""


def test_runner_verhindert_parallelen_lauf_gleichen_tools():
    mgr = RunManager()
    tool = slow_tool()
    run_id = mgr.start(tool, {})
    with pytest.raises(ToolBusy):
        mgr.start(tool, {})
    mgr.cancel(run_id)
    run = wait_done(mgr, run_id)
    assert run["status"] == "cancelled"


def test_runner_dekodiert_utf16_ausgabe():
    # sfc.exe liefert UTF-16-artige Ausgabe mit NUL-Bytes
    from src.tools import runner
    text = "Der Windows-Ressourcenschutz"
    assert runner.decode_output(text.encode("utf-16-le")) == text
    assert runner.decode_output("normal ausgabe".encode("utf-8")) == "normal ausgabe"
