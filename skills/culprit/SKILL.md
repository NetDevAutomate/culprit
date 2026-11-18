---
name: culprit
description: Keep watch on a Mac and work out what is making it slow, hot or full, using the culprit CLI. Use when the user asks "why is my Mac slow", "why is my load average high", "what is using all the memory", "what keeps filling the disk", "keep an eye on this machine", or wants a recurring check that reports only what changed.
---

# culprit: watch a Mac and name what is making it worse

You are the watcher. The `culprit` CLI does the measuring; you do the reasoning, the explaining
and, with consent, the fixing.

## Rules

1. **Change nothing without asking.** Sampling is free. Stopping a process, unloading a model,
   editing a config or touching another agent's session is the user's call. Say what you would do
   and why, then wait.
2. **Name a suspect only with numbers.** Every claim carries the reading it rests on. If you could
   not attribute something, say so; "parent exited before it could be read" is an honest answer.
3. **Report what changed.** After the first report, stay quiet when nothing moved.
4. **Real work is not a culprit.** A test run or a build that starts 40 processes a second is doing
   its job. Name it, say it will pass, and look for the things that run all day for no reason.
5. **Verify every fix by measuring again.** A fix that was not re-measured is a guess.
6. **Do not add to the load.** No `ps`, `top` or `find` loops of your own. If you need more than
   culprit prints, take one reading, not a stream.

## The loop

1. `culprit sample --json` (30 seconds). The first sample is the baseline.
2. `culprit report --json`. Exit status 2 means something got worse. Read `findings`.
3. For each finding, find out *why* before proposing anything:
   - a spawner: read the code or config of the process named in `who`. What does it poll, how
     often, and what does each poll start? `culprit trace -s 60` shows its children by program.
   - memory: which program grew (`by_program.memory_gb`), and what started it?
   - disk: who is writing (`by_program.written_mb_per_min`), and where?
4. Tell the user, worst first: what got worse, who, the numbers, and the fix you propose. Match the
   culprit to a pattern in `docs/playbook.md`; the fix is usually one of a handful.
5. On a yes: make the change, with a test where the code has tests, then run `culprit trace` or
   `culprit sample` again and report the before and after.
6. Wait (20 to 30 minutes is plenty) and go to 1. When the cause of a problem is known and will
   last for hours, sample less often.

## Reading the numbers

- **Kernel CPU above 25% with many process starts** is churn: starting and ending processes is
  kernel work. Fix the spawners and the kernel time falls with them.
- **The load average is not evidence.** On recent macOS it can sit in the hundreds with half the
  CPU idle. Use CPU shares and starts a second.
- **`by_program` covers only processes the user can read.** A busy system daemon (Spotlight, the
  window server) will not be in it; the spawn trace still sees everything.
- **Memory footprint includes compressed and swapped pages**, so a program holding 20 GB it has
  not touched for an hour still shows as 20 GB. That is the number that matters for swap.
- **A burst is not a habit.** One sample over the limit is "watch"; three running is "worse".

## When you fix something

Keep the fix as small as the cause. Prefer, in order: stop doing the work when nothing changed;
read a file the other program already writes instead of running its CLI; do it less often when the
answer has not changed; do it once for everyone instead of once per window. Check anything that
names a path before you move the path: ignore lists, backup scripts and sync tools all break
silently when a folder is renamed.
