"""Facts about processes, read from libproc and sysctl.

Nothing here starts a process. A tool that looks for what is loading a machine should not add to
the load, and `ps` in a loop is one of the commonest culprits there is.

macOS only. Every reader returns None for a process it cannot read (gone, or another user's).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import struct
import sys
from dataclasses import dataclass


class Unsupported(RuntimeError):
    """This machine is not one culprit can read (it needs macOS)."""


if sys.platform == "darwin":
    _libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    _libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
else:  # importable anywhere, so the pure parts can be tested on any platform
    _libc = _libproc = None

_PROC_PIDTBSDINFO, _BSDINFO_SIZE = 3, 136
_CTL_KERN, _KERN_PROC, _KERN_PROC_PID, _KERN_PROCARGS2 = 1, 14, 1, 49
_KINFO_PROC_SIZE, _KINFO_PPID_OFFSET = 648, 560
_RUSAGE_INFO_V2, _RUSAGE_SIZE = 2, 160


def require_macos() -> None:
    if _libproc is None:
        raise Unsupported("culprit reads libproc, which only macOS has")


@dataclass(frozen=True)
class Usage:
    """What a process has used since it started."""

    cpu_seconds: float
    footprint_bytes: int   # memory charged to it, compressed and swapped pages included
    written_bytes: int     # bytes it has written to disk


def pids() -> set[int]:
    """Every process id on the machine."""
    count = _libproc.proc_listallpids(None, 0)
    buffer = (ctypes.c_int * (count + 256))()
    count = _libproc.proc_listallpids(buffer, ctypes.sizeof(buffer))
    return {pid for pid in buffer[:count] if pid > 0}


def parent(pid: int) -> int | None:
    """The parent's pid. libproc answers for our own processes; for another user's (a setuid
    program such as `ps` runs as root) the kernel's process record answers instead."""
    info = ctypes.create_string_buffer(_BSDINFO_SIZE)
    if _libproc.proc_pidinfo(pid, _PROC_PIDTBSDINFO, 0, info, _BSDINFO_SIZE) == _BSDINFO_SIZE:
        return struct.unpack_from("I", info.raw, 16)[0]
    mib = (ctypes.c_int * 4)(_CTL_KERN, _KERN_PROC, _KERN_PROC_PID, pid)
    size = ctypes.c_size_t(_KINFO_PROC_SIZE)
    record = ctypes.create_string_buffer(_KINFO_PROC_SIZE)
    if _libc.sysctl(mib, 4, record, ctypes.byref(size), None, 0) != 0 or size.value < _KINFO_PPID_OFFSET + 4:
        return None
    return struct.unpack_from("i", record.raw, _KINFO_PPID_OFFSET)[0]


def path(pid: int) -> str | None:
    """The program a process is running."""
    buffer = ctypes.create_string_buffer(4096)
    if _libproc.proc_pidpath(pid, buffer, 4096) <= 0:
        return None
    return buffer.value.decode("utf-8", "replace")


def argv(pid: int) -> list[str] | None:
    """A process's command line. Its environment, which follows in the same kernel buffer, is never read."""
    mib = (ctypes.c_int * 3)(_CTL_KERN, _KERN_PROCARGS2, pid)
    size = ctypes.c_size_t(16384)
    buffer = ctypes.create_string_buffer(size.value)
    if _libc.sysctl(mib, 3, buffer, ctypes.byref(size), None, 0) != 0 or size.value < 8:
        return None
    return parse_procargs(buffer.raw[: size.value])


def parse_procargs(raw: bytes) -> list[str] | None:
    """KERN_PROCARGS2: an argument count, the program's path, padding, then that many arguments."""
    if len(raw) < 8:
        return None
    count = struct.unpack_from("i", raw)[0]
    rest = raw[4:]
    end = rest.find(b"\0")
    if end < 0 or count < 0:
        return None
    words = rest[end:].lstrip(b"\0").split(b"\0")
    return [word.decode("utf-8", "replace") for word in words[:count]]


_timebase: tuple[int, int] | None = None


def _ticks_to_seconds(ticks: int) -> float:
    """Mach time units to seconds (the units are not nanoseconds on Apple silicon)."""
    global _timebase
    if _timebase is None:
        info = (ctypes.c_uint32 * 2)()
        _libc.mach_timebase_info(info)
        _timebase = (info[0] or 1, info[1] or 1)
    return ticks * _timebase[0] / _timebase[1] / 1e9


def usage(pid: int) -> Usage | None:
    """CPU time, memory footprint and bytes written. Only for processes this user may read."""
    buffer = ctypes.create_string_buffer(512)
    if _libproc.proc_pid_rusage(pid, _RUSAGE_INFO_V2, buffer) != 0:
        return None
    return parse_rusage(buffer.raw[:_RUSAGE_SIZE], _ticks_to_seconds)


def parse_rusage(raw: bytes, to_seconds=lambda ticks: ticks / 1e9) -> Usage:
    """rusage_info_v2: a 16-byte uuid, then 18 counters of 8 bytes each."""
    counters = struct.unpack_from("18Q", raw, 16)
    user, system, footprint, written = counters[0], counters[1], counters[7], counters[17]
    return Usage(cpu_seconds=to_seconds(user + system), footprint_bytes=footprint, written_bytes=written)
