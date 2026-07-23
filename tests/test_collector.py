"""Collector: PowerShell-Ausgabe → normalisiertes Bundle; Minidump-Ordner."""
import pytest

from src import collector
from tests.conftest import make_dump64


def fake_ps_payload():
    return {
        "events": [
            {"time": "2026-07-10T03:34:00+02:00", "log": "System",
             "provider": "Microsoft-Windows-Kernel-Power", "id": 41, "level": 1,
             "data": {"BugcheckCode": "0", "PowerButtonTimestamp": "0"}},
        ],
        "app_events": None,          # PS 5.1 serialisiert leere Arrays gern als null
        "memdiag_events": None,
        "update_events": [
            {"time": "2026-07-08T02:00:00+02:00", "log": "System",
             "provider": "Microsoft-Windows-WindowsUpdateClient", "id": 19,
             "level": None, "data": None,
             "message": "Installation erfolgreich: KB5031234"},
        ],
        "system": {"os_name": "Microsoft Windows 11 Pro", "os_version": "10.0.26200",
                   "build": "26200", "boot_time": "2026-07-08T08:00:00+02:00",
                   "ram_gb": 31.9, "manufacturer": "X", "model": "Y",
                   "is_laptop": False, "hostname": "PC1"},
        "errors": ["Application-Log nicht lesbar"],
    }


def test_bundle_normalisiert_null_listen_und_defaults(tmp_path):
    b = collector.collect(days=7, run_ps=lambda script: fake_ps_payload(),
                          minidump_dir=str(tmp_path / "gibtsnicht"),
                          memory_dmp=str(tmp_path / "MEMORY.DMP"))
    assert b["days"] == 7
    assert isinstance(b["is_admin"], bool)
    assert b["app_events"] == []
    assert b["memdiag_events"] == []
    assert b["events"][0]["id"] == 41
    assert b["update_events"][0]["message"].startswith("Installation")
    # level null -> 4, data null -> {}
    assert b["update_events"][0]["level"] == 4
    assert b["update_events"][0]["data"] == {}
    assert b["system"]["hostname"] == "PC1"
    assert "Application-Log nicht lesbar" in b["limits"]
    assert b["memory_dmp"] is None
    assert b["minidumps"] == []


def test_minidumps_werden_gelistet_und_geparst(tmp_path):
    md = tmp_path / "Minidump"
    md.mkdir()
    (md / "071026-1234-01.dmp").write_bytes(make_dump64(0x133, (1, 0x1E00, 0, 0)))
    (md / "kaputt.dmp").write_bytes(b"XXXX" + b"\x00" * 200)
    mem = tmp_path / "MEMORY.DMP"
    mem.write_bytes(make_dump64(0x1A))

    b = collector.collect(days=7, run_ps=lambda s: {"system": {}},
                          minidump_dir=str(md), memory_dmp=str(mem))
    dumps = {d["path"]: d for d in b["minidumps"]}
    good = dumps[str(md / "071026-1234-01.dmp")]
    assert good["bugcheck"]["code"] == 0x133
    assert good["size"] > 0 and good["mtime"]
    assert dumps[str(md / "kaputt.dmp")]["bugcheck"] is None
    assert b["memory_dmp"]["path"] == str(mem)
    assert b["memory_dmp"]["size"] > 0


def test_ps_fehler_bricht_nicht_ab(tmp_path):
    def boom(script):
        raise collector.CollectorError("powershell nicht gestartet")

    b = collector.collect(days=7, run_ps=boom, minidump_dir=str(tmp_path),
                          memory_dmp=str(tmp_path / "nope"))
    assert b["events"] == []
    assert any("powershell" in l.lower() for l in b["limits"])
    assert b["system"] == {}


def test_ps_skript_enthaelt_alle_quellen():
    script = collector.build_ps_script(days=30)
    for needle in ("41,1001,6008", "WHEA-Logger", "MemoryDiagnostics-Results",
                   "WindowsUpdateClient", "'Application Error','Application Hang'",
                   "Win32_OperatingSystem", "ConvertTo-Json"):
        assert needle in script, needle


@pytest.mark.integration
def test_live_collect_auf_dieser_maschine():
    b = collector.collect(days=7)
    assert isinstance(b["is_admin"], bool)
    assert b["system"].get("hostname")
    assert isinstance(b["events"], list)
    assert isinstance(b["app_events"], list)
