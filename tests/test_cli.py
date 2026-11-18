import argparse

import pytest

from culprit import cli, sample


@pytest.mark.parametrize("text, seconds", [("30", 30.0), ("90s", 90.0), ("20m", 1200.0), ("2h", 7200.0)])
def test_lengths_of_time(text, seconds):
    assert cli._seconds(text) == seconds


def test_a_bad_length_of_time_is_refused():
    with pytest.raises(argparse.ArgumentTypeError):
        cli._seconds("soon")


def test_report_with_no_samples_says_how_to_take_one(tmp_path, monkeypatch, capsys):
    # Arrange
    monkeypatch.setenv("CULPRIT_STATE_DIR", str(tmp_path))
    # Act
    code = cli.main(["report"])
    # Assert
    assert code == 1 and "culprit sample" in capsys.readouterr().err


def test_report_exits_2_when_something_got_worse(tmp_path, monkeypatch, capsys):
    # Arrange: two samples an hour apart with memory pressure in the second
    monkeypatch.setenv("CULPRIT_STATE_DIR", str(tmp_path))
    row = {"cpu": {"user": 20.0, "system": 5.0, "idle": 75.0}, "disk": {"free_gb": 100.0, "total_gb": 500.0},
           "spawns": {"per_second": 2.0, "spawners": []}, "by_program": {"memory_gb": {"Browser.app": 12.0}}}
    calm = {"free_gb": 9.0, "compressed_gb": 1.0, "stored_gb": 2.0, "swap_used_gb": 0.0, "swap_total_gb": 1.0, "pressure": 1}
    sample.save({**row, "at": 1000, "memory": calm})
    sample.save({**row, "at": 4600, "memory": {**calm, "pressure": 2}})
    # Act
    code = cli.main(["report"])
    # Assert
    out = capsys.readouterr().out
    assert code == 2 and "[worse] macOS reports memory pressure." in out and "Browser.app" in out
