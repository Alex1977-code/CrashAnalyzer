"""Liest den Bugcheck-Code direkt aus dem Header von Kernel-Dumps.

Windows-Kernel-Dumps (C:\\Windows\\Minidump\\*.dmp, MEMORY.DMP) beginnen mit
'PAGEDU64' (64 Bit) bzw. 'PAGEDUMP' (32 Bit); der Bugcheck-Code steht an
festem Offset 0x38, dahinter die vier Parameter (u64 bzw. u32, little-endian).
User-Mode-Minidumps ('MDMP') enthalten keinen Bugcheck — dafür None.
"""
from __future__ import annotations

import struct

_HEADER_LEN = 0x60


def read_bugcheck(path: str) -> dict | None:
    try:
        with open(path, "rb") as fh:
            head = fh.read(_HEADER_LEN)
    except OSError:
        return None
    if len(head) < _HEADER_LEN:
        return None

    sig = head[0:8]
    try:
        if sig == b"PAGEDU64":
            code = struct.unpack_from("<I", head, 0x38)[0]
            params = struct.unpack_from("<4Q", head, 0x40)
            width = 16
        elif sig == b"PAGEDUMP":
            code = struct.unpack_from("<I", head, 0x38)[0]
            params = struct.unpack_from("<4I", head, 0x3C)
            width = 8
        else:
            return None
    except struct.error:
        return None

    return {
        "code": code,
        **{f"p{i + 1}": f"0x{p:0{width}X}" for i, p in enumerate(params)},
    }
