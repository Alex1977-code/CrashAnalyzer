"""Analyse-Engine: Episoden, Klassifikation, Muster, Empfehlungen."""
from datetime import timedelta

from src import engine
from tests.conftest import (BASE, app_error_1000, app_hang_1002, bugcheck_1001,
                            ev, kernel_power_41, make_bundle, ts,
                            unexpected_shutdown_6008)


def analyze(events=None, **overrides):
    return engine.analyze(make_bundle(events, **overrides))


# ---------- Klassifikation einzelner Episoden ----------

def test_bsod_mit_1001_und_dump():
    a = analyze([
        kernel_power_41(BASE),
        bugcheck_1001(BASE + timedelta(minutes=1), 0x133),
    ])
    assert len(a["episodes"]) == 1
    epi = a["episodes"][0]
    assert epi["kind"] == "bsod"
    assert epi["confidence"] == "hoch"
    assert epi["bugcheck"]["source"] == "event1001"
    assert epi["bugcheck"]["hex"] == "0x00000133"
    assert epi["bugcheck"]["name"] == "DPC_WATCHDOG_VIOLATION"
    assert "DPC_WATCHDOG_VIOLATION" in epi["title"]
    assert epi["dump_path"] == r"C:\Windows\MEMORY.DMP"
    assert "Treiber" in epi["why"]


def test_41_mit_bugcheckcode_ohne_1001():
    a = analyze([kernel_power_41(BASE, bugcheck_code=209)])
    epi = a["episodes"][0]
    assert epi["kind"] == "bsod"
    assert epi["bugcheck"]["source"] == "event41"
    assert epi["bugcheck"]["hex"] == "0x000000D1"
    assert epi["confidence"] == "hoch"


def test_nacktes_41_ist_stromverlust():
    a = analyze([kernel_power_41(BASE)])
    epi = a["episodes"][0]
    assert epi["kind"] == "power_loss"
    assert epi["confidence"] == "niedrig"
    assert epi["bugcheck"] is None
    assert "rec_cables_psu" in epi["recommendations"]


def test_power_button_gedrueckt():
    a = analyze([kernel_power_41(BASE, power_button=133668372833012345)])
    epi = a["episodes"][0]
    assert epi["kind"] == "power_button"
    assert epi["confidence"] == "mittel"
    assert "Power-Taste" in epi["what"] or "Ein/Aus" in epi["what"]


def test_whea_davor_ist_hardware():
    a = analyze([
        ev(18, "Microsoft-Windows-WHEA-Logger", BASE - timedelta(minutes=30), level=1),
        kernel_power_41(BASE),
    ])
    epi = a["episodes"][0]
    assert epi["kind"] == "hardware"
    assert any("Hardware" in e["text"] for e in epi["evidence"])


def test_disk_cluster_ist_storage():
    events = [ev(7, "disk", BASE - timedelta(hours=h)) for h in (1, 2, 3)]
    events.append(unexpected_shutdown_6008(BASE))
    a = analyze(events)
    epi = a["episodes"][0]
    assert epi["kind"] == "storage"
    assert "rec_backup_now" in epi["recommendations"]


def test_tdr_indizien_bei_gpu_bluescreen():
    a = analyze([
        ev(4101, "Display", BASE - timedelta(minutes=50)),
        ev(4101, "Display", BASE - timedelta(minutes=20)),
        kernel_power_41(BASE),
        bugcheck_1001(BASE + timedelta(minutes=1), 0x116),
    ])
    epi = a["episodes"][0]
    assert epi["kind"] == "bsod"
    assert epi["bugcheck"]["name"] == "VIDEO_TDR_FAILURE"
    assert sum("Grafik" in e["text"] for e in epi["evidence"]) == 2
    assert "rec_gpu_driver" in epi["recommendations"]


def test_minidump_liefert_code_wenn_events_keinen_haben():
    a = analyze(
        [kernel_power_41(BASE)],
        minidumps=[{"path": r"C:\Windows\Minidump\071026-1234-01.dmp", "size": 1234567,
                    "mtime": ts(BASE + timedelta(minutes=2)),
                    "bugcheck": {"code": 0x1A, "p1": "0x41790", "p2": "0x0", "p3": "0x0", "p4": "0x0"}}],
    )
    epi = a["episodes"][0]
    assert epi["kind"] == "bsod"
    assert epi["bugcheck"]["source"] == "minidump"
    assert epi["bugcheck"]["name"] == "MEMORY_MANAGEMENT"
    assert epi["dump_path"].endswith("071026-1234-01.dmp")


# ---------- Episoden-Bildung ----------

def test_41_und_6008_werden_zu_einer_episode_dedupliziert():
    a = analyze([
        kernel_power_41(BASE),
        unexpected_shutdown_6008(BASE + timedelta(minutes=2)),
    ])
    assert len(a["episodes"]) == 1


def test_saubere_shutdowns_ergeben_keine_episode():
    a = analyze([
        ev(6005, "EventLog", BASE - timedelta(hours=5)),
        ev(1074, "User32", BASE - timedelta(hours=4)),
        ev(6006, "EventLog", BASE - timedelta(hours=4)),
        ev(6005, "EventLog", BASE),
    ])
    assert a["episodes"] == []
    assert a["summary"]["crash_count"] == 0
    assert a["summary"]["stability"] == "stabil"
    assert "eine Systemabst" in a["summary"]["headline"].replace("K", "k")  # "Keine Systemabstürze…"


def test_episoden_neueste_zuerst():
    a = analyze([
        kernel_power_41(BASE),
        kernel_power_41(BASE + timedelta(days=3)),
    ])
    assert a["episodes"][0]["time"] > a["episodes"][1]["time"]


# ---------- Muster ----------

def test_muster_gleicher_code_mehrfach():
    a = analyze([
        kernel_power_41(BASE, bugcheck_code=0x133),
        kernel_power_41(BASE + timedelta(days=10), bugcheck_code=0x133),
    ])
    kinds = {p["kind"] for p in a["patterns"]}
    assert "same_code" in kinds
    assert any("DPC_WATCHDOG_VIOLATION" in p["text"] for p in a["patterns"])


def test_muster_haeufung_in_7_tagen():
    a = analyze([
        kernel_power_41(BASE),
        kernel_power_41(BASE + timedelta(days=2)),
        kernel_power_41(BASE + timedelta(days=4)),
    ])
    assert any(p["kind"] == "cluster" for p in a["patterns"])
    assert a["summary"]["stability"] == "kritisch"


def test_muster_nach_windows_update():
    upd = ev(19, "Microsoft-Windows-WindowsUpdateClient", BASE - timedelta(days=2),
             message="Installation erfolgreich: KB5031234")
    a = analyze(
        [kernel_power_41(BASE), kernel_power_41(BASE + timedelta(days=3))],
        update_events=[upd],
    )
    assert any(p["kind"] == "after_update" for p in a["patterns"])


def test_kein_update_muster_wenn_update_nach_abstuerzen():
    upd = ev(19, "Microsoft-Windows-WindowsUpdateClient", BASE + timedelta(days=9))
    a = analyze(
        [kernel_power_41(BASE), kernel_power_41(BASE + timedelta(days=3))],
        update_events=[upd],
    )
    assert not any(p["kind"] == "after_update" for p in a["patterns"])


# ---------- Sekundäres & Aggregation ----------

def test_app_crashes_gruppiert_und_gezaehlt():
    a = analyze(app_events=[
        app_error_1000(BASE - timedelta(days=1), "HiCAD.exe", "kernelbase.dll"),
        app_error_1000(BASE - timedelta(days=2), "HiCAD.exe", "kernelbase.dll"),
        app_error_1000(BASE - timedelta(days=3), "HiCAD.exe", "ntdll.dll"),
        app_hang_1002(BASE - timedelta(days=4), "Excel.exe"),
    ])
    ac = a["app_crashes"]
    assert ac["total"] == 4
    assert ac["groups"][0]["app"] == "HiCAD.exe"
    assert ac["groups"][0]["count"] == 3
    assert ac["groups"][0]["kind"] == "crash"
    assert ac["groups"][0]["top_module"] == "kernelbase.dll"
    assert a["summary"]["app_crash_count"] == 4


def test_app_crashes_mit_benannten_feldern_win11():
    # Windows 11 benennt EventData-Felder (AppName/ModuleName statt param1/param4)
    crash = ev(1000, "Application Error", BASE - timedelta(days=1), log="Application",
               AppName="TextureMesh.exe", ModuleName="ucrtbase.dll",
               ExceptionCode="c0000005")
    hang = ev(1002, "Application Hang", BASE - timedelta(days=2), log="Application",
              AppName="Notepad.exe", HangType="Cross-thread")
    a = analyze(app_events=[crash, hang])
    groups = {g["app"]: g for g in a["app_crashes"]["groups"]}
    assert groups["TextureMesh.exe"]["top_module"] == "ucrtbase.dll"
    assert groups["Notepad.exe"]["kind"] == "hang"


def test_empfehlungen_aggregiert_dedupliziert_sortiert():
    a = analyze([
        kernel_power_41(BASE, bugcheck_code=0x1A),
        kernel_power_41(BASE + timedelta(days=1), bugcheck_code=0x1A),
    ])
    recs = a["recommendations"]
    ids = [r["id"] for r in recs]
    assert len(ids) == len(set(ids)), "keine Duplikate"
    assert "rec_memtest" in ids
    prios = [r["priority"] for r in recs]
    assert prios == sorted(prios), "nach Priorität sortiert"
    assert all(r["title"] and r["category"] for r in recs)


def test_memdiag_ergebnis_wird_uebernommen():
    m = ev(1201, "Microsoft-Windows-MemoryDiagnostics-Results", BASE - timedelta(days=5),
           message="Die Windows-Speicherdiagnose hat den Computerspeicher getestet, ohne Fehler zu ermitteln.")
    a = analyze([], memdiag_events=[m])
    assert a["memdiag"]["last_run"] is not None
    assert "ohne Fehler" in a["memdiag"]["result"]


def test_laptop_stromverlust_empfiehlt_akku_pruefung():
    b = make_bundle([kernel_power_41(BASE)])
    b["system"]["is_laptop"] = True
    a = engine.analyze(b)
    assert "rec_battery" in a["episodes"][0]["recommendations"]


def test_limits_werden_durchgereicht():
    a = analyze([], limits=["Minidump-Ordner nicht lesbar (keine Administratorrechte)"])
    assert any("Minidump" in l for l in a["limits"])


def test_hauptverdacht_im_summary():
    a = analyze([
        kernel_power_41(BASE, bugcheck_code=0x133),
        kernel_power_41(BASE + timedelta(days=1), bugcheck_code=0x133),
    ])
    assert a["summary"]["crash_count"] == 2
    assert a["summary"]["main_suspect"]
    assert "2" in a["summary"]["headline"]
