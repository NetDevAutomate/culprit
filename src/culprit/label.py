"""Short names for processes that are safe to print and to keep.

A command line can hold a token, a password or a signed URL, and culprit prints command lines and
writes them to a history file. So every name passes through `redact` first.
"""

from __future__ import annotations

import os
import re

INTERPRETERS = {"python", "python3", "node", "bun", "deno", "ruby", "perl", "php", "bash", "sh", "zsh", "fish",
                "uv", "npx", "env", "java", "osascript"}
_SECRET_FLAG = re.compile(r"^--?[\w-]*(token|secret|password|passwd|api[-_]?key|apikey|auth|credential|bearer)[\w-]*$", re.I)
_SECRET_PAIR = re.compile(r"^([\w.-]*(?:token|secret|password|passwd|api[-_]?key|apikey|auth|credential)[\w.-]*)=(.+)$", re.I)
_TOKEN = re.compile(r"(?<![\w/.-])(?=[A-Za-z0-9_\-+/=]*\d)(?=[A-Za-z0-9_\-+/=]*[A-Za-z])[A-Za-z0-9_\-+/=]{24,}(?![\w/.-])")
_URL_SECRET = re.compile(r"(://[^/\s:@]+:)[^@\s]+@")
_ID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
HIDDEN = "•••"
INLINE = {"-e", "-c", "--eval", "-p", "--print"}


def redact(words: list[str]) -> list[str]:
    """Command-line words with anything secret-shaped replaced.

    Replaced: the value after a flag named like a secret (`--token x`), the value of a pair named
    like one (`API_KEY=x`), the password in a URL, and any long mixed letters-and-digits run. Paths
    are kept, since which script ran is the point.
    """
    out: list[str] = []
    hide_next = False
    for word in words:
        if hide_next:
            out.append(HIDDEN)
            hide_next = False
            continue
        if _ID.fullmatch(word):  # a session or request id, not a secret; shortened later
            out.append(word)
            continue
        if _SECRET_FLAG.match(word):
            out.append(word)
            hide_next = True
            continue
        pair = _SECRET_PAIR.match(word)
        if pair:
            out.append(f"{pair.group(1)}={HIDDEN}")
            continue
        if word == "Bearer":
            out.append(word)
            hide_next = True
            continue
        word = _URL_SECRET.sub(rf"\1{HIDDEN}@", word)
        out.append(word if "/" in word and not word.startswith("-") else _TOKEN.sub(HIDDEN, word))
    return out


def _tidy(text: str, home: str) -> str:
    text = " ".join(text.split())
    if home and home != "/":
        text = text.replace(home, "~")
    return _ID.sub(lambda m: m.group(0)[:8], text)


def program(path: str | None) -> str:
    """The program's file name, or the folder that names it when the file is only a version
    number (`.../agent/versions/2.1.3` is `agent`)."""
    if not path:
        return "(gone before it could be read)"
    name = os.path.basename(path)
    if re.fullmatch(r"[\d.]+", name):
        named = [part for part in path.split("/")[:-1] if part and part != "versions" and not re.fullmatch(r"[\d.]+", part)]
        name = named[-1] if named else name
    return name


def app_of(path: str | None) -> str | None:
    """The outermost app bundle a path is inside, unless that bundle only wraps an interpreter."""
    app = re.search(r"/([^/]+)\.app/", path or "")
    if not app or _stem(app.group(1)) in INTERPRETERS:
        return None
    return f"{app.group(1)}.app"


def describe(path: str | None, argv: list[str] | None, home: str | None = None, width: int = 90) -> str:
    """One line saying what a long-lived process is, for the list of who started things.

    An app is named by its bundle. An interpreter is named with the script it runs, since
    "python" says nothing. Everything is redacted and cut to `width`.
    """
    home = os.path.expanduser("~") if home is None else home
    name = program(path)
    interpreter = _stem(name) in INTERPRETERS
    app = re.search(r"/([^/]+\.app)/Contents/MacOS/[^/]+$", path or "")
    if app and not interpreter:  # Python's own binary sits in a Python.app, which names nothing
        return app.group(1)
    words = redact(list(argv or []))
    if not words:
        return _tidy(name, home)[:width]
    base = os.path.basename(words[0]) or name
    rest = words[1:]
    if interpreter or _stem(base) in INTERPRETERS:
        for index, word in enumerate(rest):
            if word in INLINE:  # the program is the next argument: code, not a file
                return f"{base} {word} (inline code)"
            if not word.startswith("-"):
                shown = " ".join([os.path.basename(word) if "/" in word else word, *rest[index + 1:]])
                return _tidy(f"{base} {shown}", home)[:width]
    return _tidy(" ".join([base, *rest]), home)[:width]


def _stem(name: str) -> str:
    """`python3.14` and `Python` are both python."""
    return re.sub(r"[\d.]+$", "", name.lower())
