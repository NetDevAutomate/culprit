import json
import stat

import pytest

from culprit import actions, cli


def entry(stage="planned", kind="skip-when-unchanged", **extra):
    return {"stage": stage, "kind": kind, "target": "status plugin poll", "why": "6 ps a second for 3 samples", **extra}


def test_the_full_life_of_an_optimisation_is_logged_in_order(tmp_path):
    # Arrange
    path = tmp_path / "actions.jsonl"
    # Act
    actions.add(entry(), path, now=100)
    actions.add(entry("applied", change="stat the runs folder first", undo="git revert abc123"), path, now=200)
    actions.add(entry("verified", before=6.0, after=0.0), path, now=300)
    # Assert
    rows = actions.load(path)
    assert [(row["stage"], row["at"]) for row in rows] == [("planned", 100), ("applied", 200), ("verified", 300)]
    assert all(row["automatic"] for row in rows) and stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("kind", sorted(actions.FORBIDDEN))
def test_nothing_that_stops_deletes_or_removes_can_be_logged_as_done_unattended(tmp_path, kind):
    # Act / Assert
    with pytest.raises(actions.Refused, match="never does that unattended"):
        actions.add(entry("applied", kind=kind, undo="none"), tmp_path / "a.jsonl")
    assert actions.load(tmp_path / "a.jsonl") == []


def test_an_unattended_run_can_only_note_a_forbidden_action_as_skipped(tmp_path):
    # Act
    row = actions.add(entry("skipped", kind="delete-data"), tmp_path / "a.jsonl")
    # Assert
    assert row["stage"] == "skipped" and row["automatic"] is True


def test_a_forbidden_action_a_person_approved_is_still_written_down(tmp_path):
    # Act
    row = actions.add(entry("applied", kind="delete-data", change="deleted 40 unused simulators", undo="cannot be undone"),
                      tmp_path / "a.jsonl", automatic=False)
    # Assert
    assert row["automatic"] is False and row["undo"] == "cannot be undone"


@pytest.mark.parametrize("bad, message", [
    (entry("applied", undo="x"), "planned before applying"),
    (entry("verified", before=6.0, after=1.0), "nothing was applied"),
    (entry(kind="make-it-faster"), "unknown kind"),
    ({"stage": "planned", "kind": "back-off", "target": "", "why": "x"}, "needs a target"),
])
def test_actions_out_of_order_or_unknown_are_refused(tmp_path, bad, message):
    with pytest.raises(actions.Refused, match=message):
        actions.add(bad, tmp_path / "a.jsonl")


def test_an_applied_action_must_say_how_to_undo_it(tmp_path):
    # Arrange
    path = tmp_path / "a.jsonl"
    actions.add(entry(), path)
    # Act / Assert
    with pytest.raises(actions.Refused, match="how to undo"):
        actions.add(entry("applied"), path)


def test_a_change_that_did_not_improve_the_reading_cannot_be_verified(tmp_path):
    # Arrange
    path = tmp_path / "a.jsonl"
    actions.add(entry(), path)
    actions.add(entry("applied", undo="git revert abc123"), path)
    # Act / Assert: the same or worse must be reverted, and that is logged too
    with pytest.raises(actions.Refused, match="did not improve"):
        actions.add(entry("verified", before=6.0, after=6.5), path)
    actions.add(entry("reverted", change="git revert abc123"), path)
    assert [row["stage"] for row in actions.load(path)] == ["planned", "applied", "reverted"]


def test_the_log_is_only_ever_appended_to(tmp_path):
    # Arrange
    path = tmp_path / "a.jsonl"
    actions.add(entry(), path, now=1)
    first = path.read_text()
    # Act
    actions.add(entry(kind="back-off"), path, now=2)
    # Assert
    assert path.read_text().startswith(first) and len(path.read_text().splitlines()) == 2


def test_log_command_refuses_with_exit_4_and_shows_what_was_done(tmp_path, monkeypatch, capsys):
    # Arrange
    monkeypatch.setenv("CULPRIT_STATE_DIR", str(tmp_path))
    base = ["log", "add", "--target", "dashboard repo sweep", "--why", "1,000 git every 10 minutes"]
    # Act
    refused = cli.main([*base, "--stage", "applied", "--kind", "stop-process", "--undo", "restart it"])
    planned = cli.main([*base, "--stage", "planned", "--kind", "back-off"])
    shown = cli.main(["log"])
    # Assert
    out = capsys.readouterr()
    assert (refused, planned, shown) == (4, 0, 0)
    assert "refused" in out.err and "stopping or killing" in out.err
    assert "planned  back-off: dashboard repo sweep" in out.out
    assert len(json.loads((tmp_path / "actions.jsonl").read_text().splitlines()[0])) >= 5
