"""Checks against the real machine: the struct offsets culprit reads are the kernel's."""
import os
import re
import struct
import subprocess
import sys

import pytest

from culprit import cli, procs, system

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="culprit reads macOS's libproc")


def test_procargs_and_rusage_parsers_read_their_layouts():
    # Arrange: argc 2, the path, padding, two arguments, then the environment
    raw = struct.pack("i", 2) + b"/bin/echo\0\0\0echo\0hello\0SECRET=1\0"
    counters = [0] * 18
    counters[0], counters[1], counters[7], counters[17] = 2_000_000_000, 1_000_000_000, 4096, 512
    # Act / Assert: the environment is never returned
    assert procs.parse_procargs(raw) == ["echo", "hello"]
    assert procs.parse_rusage(b"\0" * 16 + struct.pack("18Q", *counters)) == procs.Usage(3.0, 4096, 512)


def test_this_process_reads_as_itself():
    me = os.getpid()
    assert me in procs.pids()
    assert procs.parent(me) == os.getppid()
    assert os.path.basename(procs.path(me)).lower().startswith("python")
    assert procs.argv(me)[0].lower().find("python") >= 0
    used = procs.usage(me)
    assert used.cpu_seconds > 0 and used.footprint_bytes > 1_000_000


def test_a_root_owned_process_still_has_a_parent():
    # launchd is root's; its parent is the kernel (0)
    assert procs.parent(1) == 0


def test_memory_matches_vm_stat():
    # Arrange: what Apple's own tool says
    out = subprocess.run(["vm_stat"], capture_output=True, text=True, check=True).stdout
    page = int(re.search(r"page size of (\d+)", out).group(1))
    pages = lambda name: int(re.search(name + r":\s+(\d+)", out).group(1)) * page / 2**30
    # Act
    memory = system.memory()
    # Assert: the same counters, a moment apart
    assert memory.compressed_gb == pytest.approx(pages("Pages occupied by compressor"), abs=2.0)
    assert memory.stored_gb == pytest.approx(pages("Pages stored in compressor"), abs=3.0)
    assert memory.pressure in (1, 2, 4) and memory.swap_total_gb >= memory.swap_used_gb >= 0


def test_cpu_and_disk_are_sane():
    before = system.cpu_ticks()
    sum(i * i for i in range(300_000))
    share = system.cpu_share(before, system.cpu_ticks())
    assert 99.0 <= share["user"] + share["system"] + share["idle"] <= 101.0
    disk = system.disk()
    assert 0 < disk.free_gb < disk.total_gb


def test_trace_command_prints_json(capsys):
    # Act
    code = cli.main(["trace", "-s", "1", "--json"])
    # Assert
    out = capsys.readouterr().out
    assert code == 0 and '"spawners"' in out and '"per_second"' in out
