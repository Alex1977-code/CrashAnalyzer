"""Gemeinsame Fixture-Bausteine: synthetische Event-Bundles wie vom Collector."""
from __future__ import annotations

import struct
from datetime import datetime, timedelta, timezone


def make_dump64(code: int, params: tuple[int, int, int, int] = (0, 0, 0, 0)) -> bytes:
    """Synthetischer 64-Bit-Kernel-Dump-Header (PAGEDU64-Layout)."""
    buf = bytearray(b"\x00" * 0x2000)
    buf[0:8] = b"PAGEDU64"
    struct.pack_into("<I", buf, 0x38, code)
    for i, p in enumerate(params):
        struct.pack_into("<Q", buf, 0x40 + 8 * i, p)
    return bytes(buf)

TZ = timezone(timedelta(hours=2))
BASE = datetime(2026, 7, 10, 3, 34, 0, tzinfo=TZ)


def ts(dt: datetime) -> str:
    return dt.isoformat()


def ev(event_id: int, provider: str, dt: datetime, log: str = "System",
       level: int = 2, message: str | None = None, **data) -> dict:
    e = {
        "time": ts(dt),
        "log": log,
        "provider": provider,
        "id": event_id,
        "level": level,
        "data": {k: str(v) for k, v in data.items()},
    }
    if message is not None:
        e["message"] = message
    return e


def kernel_power_41(dt: datetime, bugcheck_code: int = 0, power_button: int = 0) -> dict:
    return ev(41, "Microsoft-Windows-Kernel-Power", dt, level=1,
              BugcheckCode=bugcheck_code, BugcheckParameter1="0x0",
              BugcheckParameter2="0x0", BugcheckParameter3="0x0",
              BugcheckParameter4="0x0", PowerButtonTimestamp=power_button,
              SleepInProgress=0)


def bugcheck_1001(dt: datetime, code: int, dump: str = r"C:\Windows\MEMORY.DMP") -> dict:
    params = f"0x{code:08x} (0x0000000000000001, 0x0000000000001e00, 0x0000000000000000, 0x0000000000000000)"
    return ev(1001, "Microsoft-Windows-WER-SystemErrorReporting", dt,
              param1=params, param2=dump, param3="ab12cd34-...")


def unexpected_shutdown_6008(dt: datetime) -> dict:
    return ev(6008, "EventLog", dt)


def app_error_1000(dt: datetime, app: str, module: str = "ntdll.dll") -> dict:
    return ev(1000, "Application Error", dt, log="Application",
              param1=app, param2="1.0.0.0", param3="abc", param4=module)


def app_hang_1002(dt: datetime, app: str) -> dict:
    return ev(1002, "Application Hang", dt, log="Application", param1=app)


def make_bundle(events=None, **overrides) -> dict:
    b = {
        "collected_at": ts(BASE + timedelta(days=1)),
        "days": 30,
        "is_admin": True,
        "system": {
            "os_name": "Microsoft Windows 11 Pro", "os_version": "10.0.26200",
            "build": "26200", "boot_time": ts(BASE - timedelta(days=2)),
            "ram_gb": 32.0, "manufacturer": "TestCorp", "model": "Box 3000",
            "is_laptop": False, "hostname": "TESTPC",
        },
        "events": events or [],
        "app_events": [],
        "memdiag_events": [],
        "update_events": [],
        "minidumps": [],
        "memory_dmp": None,
        "limits": [],
    }
    b.update(overrides)
    return b
