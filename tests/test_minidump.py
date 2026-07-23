"""Minidump-Header-Parser: Bugcheck-Code direkt aus .dmp-Dateien."""
import struct

from src import minidump
from tests.conftest import make_dump64 as _dump64


def _dump32(code: int, params: tuple[int, int, int, int]) -> bytes:
    buf = bytearray(b"\x00" * 0x1000)
    buf[0:8] = b"PAGEDUMP"
    struct.pack_into("<I", buf, 0x38, code)
    for i, p in enumerate(params):
        struct.pack_into("<I", buf, 0x3C + 4 * i, p)
    return bytes(buf)


def test_pagedu64_liefert_code_und_parameter(tmp_path):
    f = tmp_path / "071026-1234-01.dmp"
    f.write_bytes(_dump64(0x133, (0x1, 0x1E00, 0x0, 0x0)))
    bc = minidump.read_bugcheck(str(f))
    assert bc["code"] == 0x133
    assert bc["p1"] == "0x0000000000000001"
    assert bc["p2"] == "0x0000000000001E00"


def test_pagedump_32bit_wird_gelesen(tmp_path):
    f = tmp_path / "old.dmp"
    f.write_bytes(_dump32(0x1A, (0x41790, 0, 0, 0)))
    bc = minidump.read_bugcheck(str(f))
    assert bc["code"] == 0x1A
    assert bc["p1"] == "0x00041790"


def test_unbekannte_signatur_gibt_none(tmp_path):
    f = tmp_path / "garbage.dmp"
    f.write_bytes(b"MDMP" + b"\x00" * 100)  # User-Mode-Minidump-Signatur
    assert minidump.read_bugcheck(str(f)) is None


def test_trunkierte_datei_gibt_none(tmp_path):
    f = tmp_path / "short.dmp"
    f.write_bytes(b"PAGEDU64" + b"\x00" * 8)
    assert minidump.read_bugcheck(str(f)) is None


def test_unlesbare_datei_gibt_none(tmp_path):
    assert minidump.read_bugcheck(str(tmp_path / "fehlt.dmp")) is None
