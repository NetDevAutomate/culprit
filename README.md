# culprit

Find what is making your Mac worse: who is starting processes, eating memory and filling the disk.

`top` and Activity Monitor show you what is busy *right now*. They cannot show a process that lives
for 20 milliseconds, and a few dozen of those a second will take whole cores, most of it kernel
time, while every list of "top processes" looks calm. culprit catches them and names the long-lived
program that keeps starting them.

- No root, no dependencies, one small Python package.
- It starts no processes itself. A monitor that runs `ps` in a loop is part of the problem.
- Command lines are redacted before they are printed or kept.
- macOS only (it reads `libproc`).

## Install

```bash
uv tool install git+https://github.com/jhammant/culprit
# or
pipx install git+https://github.com/jhammant/culprit
```

## Use

```bash
culprit trace            # who is starting processes, over 30 seconds
culprit sample           # one full sample, added to the history
culprit report           # what got worse since the earlier samples, and who is behind it
culprit watch --every 20m
```

The output below is from a real machine with the names changed. `culprit trace` charges every
process that started during the trace to the nearest ancestor that was already running:

```text
1,247 processes started in 30 s: 41.6 a second

who started them (the nearest ancestor that was already running)
   12.40/s  python3 dashboard.py --serve 8080 [1796]
            211 git, 98 ps, 41 security
    8.10/s  Sidebar.app [1818]
            160 ps, 59 security, 18 agent
    6.25/s  agent --resume 4f1c9a2e [25899]
            120 ps, 30 uv, 30 Python
    0.40/s  python3 waker.py [1717]
            12 docker
```

`culprit sample` adds CPU, memory, swap, disk and the biggest users of each, by app:

```text
20:14  CPU 26% user, 23% kernel, 52% idle  |  swap 9 of 10 GB, 28.8 GB compressed, pressure 1  |  disk 113 GB free  |  54 processes started a second
  CPU (cores): Containers.app 1.67, Terminal.app 0.85, Editor.app 0.8
  memory (GB): node (Models.app) 44.1, Browser.app 14.6, Containers.app 13.3
  disk writes (MB/min): Builder.app 6.9, Containers.app 6.6
```

`culprit report` compares the newest sample with the earlier ones. Every finding names a suspect
and the numbers it rests on:

```text
[worse] Swap grew 2.4 GB to 9 GB since the last sample. Suspect: node (Models.app) +22 GB. (memory pressure level 1, 2.3 GB free)
[worse] Free disk fell 89 GB in 4.4 h to 113 GB. Suspect: Builder.app 6.9 MB/min. (at this rate it is full in 6 h)
[watch] One process is starting 6 processes a second. Suspect: python3 dashboard.py --serve 8080. (mostly 90 git)
[better] A process that was starting 39 processes a second has stopped. Suspect: pytest -q. (now 0 a second)
```

`report` exits 2 when something got worse, so a script or an agent can act on it. Every command
takes `--json`.

## The loop: let an agent keep watch

culprit was built during one long session of asking an AI coding agent "why is my load average so
high again?". The useful part turned out to be a loop: sample, name the culprit, fix it with
consent, sample again to prove the fix. `skills/culprit/SKILL.md` is that loop written down as a
Claude Code skill. Copy the folder into `~/.claude/skills/` and ask the agent to "keep an eye on
this Mac". It reports only what changed, and it never changes anything without asking.

[docs/playbook.md](docs/playbook.md) lists the kinds of culprit it found and the fix for each. In
that session process starts went from 29 to 43 a second down to about 10 with the machine otherwise
quiet, and none of the fixes removed a feature.

## How it works

- **Spawn tracing.** The process table is listed every few milliseconds through
  `proc_listallpids`. Each new pid is read once for its parent and program, then again while it
  lives, because a fork looks like its parent until it execs. After the trace, each new process is
  walked up its parents to the first one that existed when the trace began.
- **Other users' processes.** `ps` itself is setuid root, so `libproc` will not give its parent to
  an ordinary user. The kernel's process record (`sysctl kern.proc.pid`) does.
- **Per-program numbers.** `proc_pid_rusage` gives CPU time, memory footprint (compressed and
  swapped pages included) and bytes written, read at the start and end of the window.
- **Machine numbers.** `host_statistics64` for memory and the compressor, `host_statistics` for
  CPU, `sysctl` for swap and the memory pressure level, `statvfs` for disk.

## What it cannot see

- A process that starts and exits between two looks (a few milliseconds) is missed. One whose
  parent has already exited is listed as "parent exited before it could be read", never guessed.
- CPU, memory and disk writes by program cover the processes your user may read. System daemons
  (WindowServer, Spotlight, the kernel) are missing from those three lists unless you run culprit
  with `sudo`. The spawn trace covers every process either way.
- The load average. On recent macOS it can read in the hundreds while half the CPU is idle, so
  culprit reports CPU shares and process starts and leaves it out.

## Privacy

Command lines can hold tokens and passwords. Before anything is printed or saved, culprit replaces
the value after a flag named like a secret (`--token`, `--api-key`), the value of a pair named like
one (`API_KEY=…`), passwords inside URLs, and any long run of mixed letters and digits. A
process's environment is never read. The history file
(`~/.local/state/culprit/history.jsonl`) is readable by you alone and capped at 2,000 samples.
Nothing leaves the machine.

## Development

```bash
uv run pytest
```

The tests cover the attribution, the findings and the redaction with made-up process tables, and
check the struct offsets against the running kernel on macOS.

## Licence

MIT.
