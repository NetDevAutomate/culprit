from culprit import trace as tracing
from culprit.trace import Proc


def proc(pid, ppid, path, *argv):
    return Proc(pid=pid, ppid=ppid, path=path, argv=list(argv) or None)


def test_new_processes_are_charged_to_the_ancestor_that_was_already_running():
    # Arrange: a poller that starts a shell, which starts ps twice; an app that starts one helper
    base = {1: proc(1, 0, "/sbin/launchd", "launchd"),
            10: proc(10, 1, "/usr/bin/python3", "python3", "/h/me/poller.py"),
            20: proc(20, 1, "/Applications/Thing.app/Contents/MacOS/Thing", "Thing")}
    known = {**base,
             100: proc(100, 10, "/bin/sh", "sh", "-c", "ps -p 1"),
             101: proc(101, 100, "/bin/ps", "ps", "-p", "1"),
             102: proc(102, 100, "/bin/ps", "ps", "-p", "1"),
             200: proc(200, 20, "/usr/bin/helper", "helper")}
    # Act
    traced = tracing.attribute(base, known, seconds=2.0, home="/h/me", own_pid=999)
    # Assert
    assert traced.started == 4 and traced.per_second == 2.0
    assert [(s.who, s.pid, s.count) for s in traced.spawners] == [("python3 poller.py", 10, 3), ("Thing.app", 20, 1)]
    assert traced.spawners[0].programs == {"ps": 2, "sh": 1}
    assert traced.by_program == {"ps": 2, "sh": 1, "helper": 1}


def test_a_helper_is_named_with_the_app_that_started_it():
    # Arrange: an app's inline-script helper, running since before the trace, starts ps
    base = {30: proc(30, 1, "/Applications/Models.app/Contents/MacOS/Models", "Models"),
            31: proc(31, 30, "/h/me/.models/node", "node", "-e", "watch()")}
    known = {**base, 400: proc(400, 31, "/bin/ps", "ps")}
    # Act
    traced = tracing.attribute(base, known, seconds=1.0, home="/h/me", own_pid=999)
    # Assert
    assert [s.who for s in traced.spawners] == ["node -e (inline code) (started by Models.app)"]


def test_what_launchd_starts_is_named_by_the_job_not_by_launchd():
    # Arrange: a scheduled job that ran twice, each run starting a child; and a one-off
    base = {1: proc(1, 0, "/sbin/launchd", "launchd")}
    known = {**base,
             100: proc(100, 1, "/bin/bash", "bash", "/h/me/jobs/sync.sh"), 101: proc(101, 100, "/usr/bin/rsync", "rsync"),
             200: proc(200, 1, "/bin/bash", "bash", "/h/me/jobs/sync.sh"), 201: proc(201, 200, "/usr/bin/rsync", "rsync"),
             300: proc(300, 1, "/usr/libexec/helperd", "helperd")}
    # Act
    traced = tracing.attribute(base, known, seconds=1.0, home="/h/me", own_pid=999)
    # Assert
    assert [(s.who, s.pid, s.count) for s in traced.spawners] == [
        ("bash sync.sh (a job launchd starts)", None, 4), ("helperd (a job launchd starts)", None, 1)]


def test_a_process_whose_parent_was_never_seen_is_an_orphan_not_a_guess():
    # Arrange: pid 300's parent 250 came and went between two looks
    base = {2: proc(2, 0, "/usr/bin/other", "other")}
    known = {**base, 300: proc(300, 250, None)}
    # Act
    traced = tracing.attribute(base, known, seconds=1.0, own_pid=999)
    # Assert
    assert [(s.who, s.pid) for s in traced.spawners] == [(tracing.ORPHAN, None)]
    assert traced.by_program == {tracing.UNREAD: 1}


def test_what_culprit_starts_itself_is_left_out():
    # Arrange: culprit is pid 50 and has a child
    base = {50: proc(50, 1, "/usr/bin/python3", "python3", "-m", "culprit")}
    known = {**base, 500: proc(500, 50, "/bin/echo", "echo")}
    # Act
    traced = tracing.attribute(base, known, seconds=1.0, own_pid=50)
    # Assert
    assert traced.started == 0 and traced.spawners == []


def test_observe_reads_a_new_process_again_after_it_execs():
    # Arrange: pid 7 appears as a copy of its parent, then becomes git; time moves 1 s a look
    tables = [{1}, {1, 7}, {1, 7}, {1}]
    looks = {"n": 0}
    reads = {7: [proc(7, 1, "/bin/zsh", "zsh"), proc(7, 1, "/usr/bin/git", "git", "status")]}

    def list_pids():
        looks["n"] += 1
        return tables[min(looks["n"] - 1, len(tables) - 1)]

    def read(pid):
        return proc(1, 0, "/sbin/launchd") if pid == 1 else (reads[7].pop(0) if len(reads[7]) > 1 else reads[7][0])

    now = {"t": 0.0}

    def clock():
        now["t"] += 0.5
        return now["t"]

    # Act
    base, known, elapsed = tracing.observe(3.0, list_pids=list_pids, read_proc=read, clock=clock, sleep=lambda s: None)
    # Assert
    assert set(base) == {1} and known[7].path == "/usr/bin/git" and known[7].argv == ["git", "status"]
    assert elapsed >= 3.0
