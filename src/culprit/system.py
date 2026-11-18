"""Whole-machine readings: CPU, memory, swap and disk, from Mach and sysctl. No process is started."""

from __future__ import annotations

import ctypes
import os
import struct
from dataclasses import dataclass

from . import procs

_HOST_CPU_LOAD_INFO, _HOST_VM_INFO64, _VM_INFO64_WORDS = 3, 4, 38
DATA_VOLUME = "/System/Volumes/Data"


@dataclass(frozen=True)
class CpuTicks:
    user: int
    system: int
    idle: int


@dataclass(frozen=True)
class Memory:
    free_gb: float
    compressed_gb: float      # RAM the compressor occupies
    stored_gb: float          # what that RAM holds, before compression
    swap_used_gb: float
    swap_total_gb: float
    pressure: int             # 1 normal, 2 warn, 4 critical (the kernel's own levels)


@dataclass(frozen=True)
class Disk:
    free_gb: float
    total_gb: float


def _host() -> int:
    libc = procs._libc
    libc.mach_host_self.restype = ctypes.c_uint
    return libc.mach_host_self()


def cpu_ticks() -> CpuTicks:
    """CPU time since boot, all cores together. Two readings give the share over the time between."""
    words = (ctypes.c_uint * 4)()
    count = ctypes.c_uint(4)
    procs._libc.host_statistics(_host(), _HOST_CPU_LOAD_INFO, words, ctypes.byref(count))
    user, system, idle, nice = words
    return CpuTicks(user=user + nice, system=system, idle=idle)


def cpu_share(before: CpuTicks, after: CpuTicks) -> dict[str, float]:
    """Percent of all cores spent in user code, in the kernel and idle between two readings."""
    user, system, idle = after.user - before.user, after.system - before.system, after.idle - before.idle
    total = (user + system + idle) or 1
    return {"user": round(100 * user / total, 1), "system": round(100 * system / total, 1),
            "idle": round(100 * idle / total, 1)}


def parse_vm_info(raw: bytes, page_size: int) -> dict[str, float]:
    """vm_statistics64 in GB: the page counts culprit reports, picked out of the kernel's struct."""
    free, _active, _inactive, _wired = struct.unpack_from("4I", raw, 0)
    compressor_pages = struct.unpack_from("I", raw, 128)[0]
    stored_pages = struct.unpack_from("Q", raw, 144)[0]
    gb = page_size / 2**30
    return {"free_gb": round(free * gb, 1), "compressed_gb": round(compressor_pages * gb, 1),
            "stored_gb": round(stored_pages * gb, 1)}


def _sysctl(name: str, size: int) -> bytes | None:
    buffer = ctypes.create_string_buffer(size)
    length = ctypes.c_size_t(size)
    if procs._libc.sysctlbyname(name.encode(), buffer, ctypes.byref(length), None, 0) != 0:
        return None
    return buffer.raw[: length.value]


def memory() -> Memory:
    words = (ctypes.c_uint * _VM_INFO64_WORDS)()
    count = ctypes.c_uint(_VM_INFO64_WORDS)
    procs._libc.host_statistics64(_host(), _HOST_VM_INFO64, words, ctypes.byref(count))
    vm = parse_vm_info(bytes(words), os.sysconf("SC_PAGE_SIZE"))
    swap = _sysctl("vm.swapusage", 32)
    total, _available, used = struct.unpack_from("3Q", swap) if swap and len(swap) >= 24 else (0, 0, 0)
    level = _sysctl("kern.memorystatus_vm_pressure_level", 4)
    return Memory(swap_used_gb=round(used / 2**30, 1), swap_total_gb=round(total / 2**30, 1),
                  pressure=struct.unpack("i", level)[0] if level and len(level) == 4 else 0, **vm)


def disk(volume: str = DATA_VOLUME) -> Disk:
    """Space really free on the data volume (Finder's figure counts space it could purge)."""
    stat = os.statvfs(volume if os.path.exists(volume) else "/")
    return Disk(free_gb=round(stat.f_bavail * stat.f_frsize / 2**30, 1),
                total_gb=round(stat.f_blocks * stat.f_frsize / 2**30, 1))
