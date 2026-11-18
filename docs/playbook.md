# Playbook: the culprits, and the fix for each

These are the patterns culprit found on one developer's Mac in a single evening, with the fix that
worked. The machine had about 25 AI coding sessions open, a menu bar full of small tools and a few
dozen background jobs. Nothing here is exotic; every one is an innocent-looking line of code.

Numbers are processes started per second unless they say otherwise.

## 1. The per-window poller

**Seen:** every open agent window ran a status plugin that started a shell, a package runner and an
interpreter every 20 seconds to ask "is there a job of mine running?". The answer was no in nearly
every window. Cost: about 3 a second all day, before counting item 2.

**Fix:** before starting anything, stat the folder the answer comes from. If it has not changed
since the last look, the answer has not changed either. One `stat` replaced three processes.

**Pattern:** a poll whose answer is almost always "nothing new" should check a timestamp first.

## 2. `ps` to ask about a process that is gone

**Seen:** the same plugin checked five long-dead jobs on every poll by running `ps` on each
recorded pid. 25 windows × 5 pids every 20 seconds was 6 `ps` a second, the single most-started
program on the machine.

**Fix:** `kill(pid, 0)` first. A pid that does not exist needs no `ps`.

**Pattern:** records of things that crashed never get marked finished. Anything that loops over
them pays for every one, forever.

## 3. Running a CLI to read a file it prints

**Seen:** two tools listed the agent sessions by running the agent's own CLI every few seconds. One
run of that command started about 28 processes (a `ps` per session, and the keychain). The command
prints from a folder of small JSON files.

**Fix:** read the files. Keep the command as a fallback, and as a cross-check every few minutes,
since the file layout is not a promise.

**Pattern:** if a command's output comes from files you can read, polling the command is paying
for a process tree to do `cat`.

## 4. The same question asked by two programs

**Seen:** culprits 3a and 3b were two separate apps polling the same command.

**Fix:** here, both moved to the files. Otherwise: one of them serves the answer to the other.

## 5. Re-checking what has not changed

**Seen:** a dashboard ran up to three `git` commands in each of about 170 old working folders every
ten minutes: 500 to 1,000 `git` a sweep, mostly for folders of work that had long finished.

**Fix:** back off. A folder that reads the same as last time is checked half as often each time,
down to hourly; any change brings it back. And one `git status --branch` already says how far
ahead a branch is, so the second command was not needed where there is an upstream.

**Pattern:** unchanged things should get cheaper to watch over time.

## 6. A daemon listing containers every two seconds

**Seen:** a small supervisor ran `docker ps` every 2 seconds to find containers that only it
creates or removes.

**Fix:** list every 30 seconds, and at once after its own changes.

**Pattern:** if you are the only writer, you already know the state.

## 7. Version-manager shims

**Seen:** every `node` call went through a version manager's shim, which ran a small script once
per parent folder to look for legacy version files. 84 of the 219 processes a single agent session
started at launch were that one script.

**Fix:** turn the legacy-file lookup off and give the three projects that used one an explicit
version file.

**Pattern:** a shim's cost is multiplied by everything that calls the tool. Measure one call.

## 8. The indexer and the log folder

**Seen:** 270 MB of job logs lived inside an indexed folder. About 15 of them were appended to
every two minutes, some of them 20 to 97 MB, and the search indexer re-read each one every time.

**Fix:** keep logs somewhere the indexer skips (on macOS, a folder whose name ends in `.noindex`).

**Watch out:** moving the folder took it out from under a sync tool's ignore rule, and the sync
tool started hashing the logs instead. Check every ignore list that names a path before moving it.

## 9. A backup copy that gets indexed

**Seen:** a nightly copy of the whole projects folder into a cloud drive was indexed too, so every
file was indexed twice.

**Fix:** the copy's folder also ends in `.noindex` now.

## 10. Big models loaded while the day is still going

**Seen:** a nightly job loaded 22 GB of local models at 20:00 on top of a 16 GB one already idle
in memory, while 25 sessions, phone simulators and several container stacks were still open. Swap
went from 6.6 to 11.2 GB in under an hour.

**Not a bug:** the job was doing what it was built to do. The fix is scheduling: start it when the
day's work has closed, or have it wait for free memory.

**Pattern:** not every culprit is a mistake. Say what it is and let the owner decide.

## 11. Real work

**Seen:** the largest spawner of the evening, 40 to 60 a second, was a test suite that runs
`git` for nearly every test.

**Fix:** none. It ended. A watcher that accuses real work stops being listened to.
