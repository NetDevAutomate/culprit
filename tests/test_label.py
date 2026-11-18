import pytest

from culprit import label


@pytest.mark.parametrize("words, expected", [
    (["curl", "--token", "abc123", "https://example.com"], ["curl", "--token", label.HIDDEN, "https://example.com"]),
    (["env", "API_KEY=" + "not-a-real-key-123", "run"], ["env", f"API_KEY={label.HIDDEN}", "run"]),
    (["curl", "-H", "Authorization:", "Bearer", "eyJhbGciOi"], ["curl", "-H", "Authorization:", "Bearer", label.HIDDEN]),
    (["psql", "postgres://app:hunter2@db.example.com/x"], ["psql", f"postgres://app:{label.HIDDEN}@db.example.com/x"]),
    (["tool", "made" + "up" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4"], ["tool", label.HIDDEN]),
])
def test_redact_hides_what_looks_like_a_secret(words, expected):
    # Act
    shown = label.redact(words)
    # Assert
    assert shown == expected


def test_redact_keeps_paths_flags_and_ids():
    # Arrange: a long path, a plain flag, and a session id, none of them secret
    words = ["python", "/Users/someone/projects/a-very-long-folder-name-2026/run_everything.py", "--resume",
             "d16b24c6-726b-4129-9b1d-26f3c4486014", "--verbose"]
    # Act / Assert
    assert label.redact(words) == words


@pytest.mark.parametrize("path, argv, expected", [
    ("/Applications/Thing.app/Contents/MacOS/Thing", ["/Applications/Thing.app/Contents/MacOS/Thing"], "Thing.app"),
    ("/opt/python/Python.app/Contents/MacOS/Python", ["python3", "/h/me/tools/sync.py", "--serve", "8080"],
     "python3 sync.py --serve 8080"),
    ("/usr/local/bin/node", ["node", "-e", "function a() { return 1 }"], "node -e (inline code)"),
    ("/usr/bin/git", ["git", "-C", "/h/me/repo", "status"], "git -C ~/repo status"),
    ("/usr/local/bin/agent", ["agent", "--resume", "d16b24c6-726b-4129-9b1d-26f3c4486014"], "agent --resume d16b24c6"),
    ("/usr/bin/tool", None, "tool"),
])
def test_describe_names_what_a_process_is(path, argv, expected):
    # Act
    shown = label.describe(path, argv, home="/h/me")
    # Assert
    assert shown == expected


def test_describe_never_shows_a_token_from_the_command_line():
    # Act
    shown = label.describe("/usr/bin/curl", ["curl", "--api-key", "s3cr3t", "https://example.com"], home="/h/me")
    # Assert
    assert "s3cr3t" not in shown
