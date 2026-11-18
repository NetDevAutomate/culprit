"""The action log: everything that was changed in culprit's name, and how to undo it.

culprit itself never changes anything. An agent following the skill may, and when it runs
unattended it is held to two rules this file enforces on what it records. This is a gate and a
record, not a sandbox: it cannot stop an agent that never calls it, which is why the skill makes
logging the first step of every action and treats a refusal as a stop.

1. Only optimisations. Each action declares its kind, and only the kinds in `ALLOWED` can be logged
   as applied in automatic mode. They all do the same work more cheaply; none stops work, removes
   data or removes a feature.
2. Everything is written down first. An action is logged as `planned` before it is made, then as
   `applied` with how to undo it, then as `verified` or `reverted` once it has been measured.

The log is append-only: entries are never edited or removed by this code.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import sample

# What an unattended run may do, and what each one means.
ALLOWED = {
    "poll-less-often": "do the same check less often when its answer has not changed",
    "skip-when-unchanged": "check a timestamp or a file before doing the work, and skip it when nothing changed",
    "read-instead-of-run": "read a file a program already writes instead of running the program to print it",
    "share-one-poll": "ask once and share the answer instead of asking from several places",
    "back-off": "check unchanged things less and less often, and return to normal when one changes",
    "cheaper-call": "get the same answer from fewer or lighter commands",
    "exclude-from-indexing": "keep generated files (logs, caches, copies) out of search indexing",
    "lower-priority": "run a background process at lower priority, without stopping it",
}
# What no unattended run may do, whatever it is called. Listed so a refusal can say why.
FORBIDDEN = {
    "stop-process": "stopping or killing a process or job",
    "delete-data": "deleting files, caches, logs, simulators, images or snapshots",
    "remove-feature": "turning a feature off or removing it",
    "change-schedule": "moving or disabling a scheduled job",
    "unload": "unloading models or quitting apps",
    "other-peoples-work": "editing another session's or person's uncommitted work",
}
STAGES = ("planned", "applied", "verified", "reverted", "skipped")


class Refused(ValueError):
    """An action that may not be logged as it stands; the message says why."""


def log_path() -> Path:
    return sample.history_path().with_name("actions.jsonl")


def load(path: Path | None = None) -> list[dict]:
    path = path or log_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def check(entry: dict, earlier: list[dict], automatic: bool) -> None:
    """Refuse an entry that breaks the rules. `earlier` is the log so far."""
    stage, kind, target = entry.get("stage"), entry.get("kind"), entry.get("target")
    if stage not in STAGES:
        raise Refused(f"stage must be one of {', '.join(STAGES)}")
    if not target or not entry.get("why"):
        raise Refused("an action needs a target (what was changed) and a why (the finding behind it)")
    if kind in FORBIDDEN:
        if automatic and stage != "skipped":  # a person may approve one; an unattended run may only note it
            raise Refused(f"'{kind}' is {FORBIDDEN[kind]}: culprit never does that unattended. "
                          "Ask the person, or log it as skipped.")
    elif kind not in ALLOWED:
        raise Refused(f"unknown kind '{kind}'. Automatic mode allows only: {', '.join(ALLOWED)}")
    same = [row for row in earlier if row.get("target") == target and row.get("kind") == kind]
    if stage == "applied":
        if not entry.get("undo"):
            raise Refused("an applied action must say how to undo it")
        if automatic and not any(row.get("stage") == "planned" for row in same):
            raise Refused("log the action as planned before applying it")
    if stage in ("verified", "reverted") and not any(row.get("stage") == "applied" for row in same):
        raise Refused(f"nothing was applied to '{target}' as '{kind}', so there is nothing to mark {stage}")
    if stage == "verified":
        before, after = entry.get("before"), entry.get("after")
        if before is None or after is None:
            raise Refused("verifying needs the reading before and after")
        if after >= before:
            raise Refused(f"the reading did not improve ({before:g} to {after:g}): revert the change and log it as reverted")


def add(entry: dict, path: Path | None = None, automatic: bool = True, now: float | None = None) -> dict:
    """Check an entry and append it. Returns the entry as written."""
    path = path or log_path()
    check(entry, load(path), automatic)
    row = {"at": round(time.time() if now is None else now), "automatic": automatic,
           **{key: value for key, value in entry.items() if value is not None}}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    return row


def line(row: dict) -> str:
    when = time.strftime("%d %b %H:%M", time.localtime(row.get("at", 0)))
    numbers = f" ({row['before']:g} to {row['after']:g} {row.get('unit', '')})".rstrip() if "before" in row and "after" in row else ""
    undo = f"\n      undo: {row['undo']}" if row.get("undo") else ""
    return (f"{when}  {row.get('stage', '?'):8s} {row.get('kind', '?')}: {row.get('target', '?')}{numbers}\n"
            f"      why: {row.get('why', '')}" + (f"\n      what: {row['change']}" if row.get("change") else "") + undo)
