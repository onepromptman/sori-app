"""Logging for Sori: one setup call per process, a run id on every line.

The engine modules (app.py, training.py, transcribe.py, deck_render.py) log
through ``logging.getLogger(__name__)``. Each entry point (app.py, shows.py,
settings.py, train.py, transcribe.py) calls ``setup()`` once at the top of
``main()``. What the CLIs print for you to read stays on stdout as plain text;
log lines go to stderr, and app.py also appends them to ``sori.log`` in your
Sori folder (rotated: 2 MB, three old copies kept), because the packaged
window app has no console.

    LOG_LEVEL   WARNING (default): only problems. INFO or DEBUG for more.
    LOG_FORMAT  text (default), or json for one JSON object per line.

Every line carries the run id, so the runs in one log file can be told apart.
What a log line may hold: host names, file names, error classes and short
error messages. What it never holds: the API key, transcript text, a full URL
(query strings carry private feed tokens) or a full local path (paths carry
your user name). Callers pass ``source()`` of a URL or path, and every line,
including exception text and tracebacks, goes through ``redact()`` on the way
out as a backstop.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s [run %(run_id)s] %(message)s"
LOG_FILE_MAX_BYTES = 2_000_000
LOG_FILE_BACKUPS = 3

_run_id: str | None = None
_handlers: list[logging.Handler] = []

# Anything with a scheme: http(s), file, ... up to whitespace or a quote.
_URL = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s'\"<>]+")
# Windows drive or UNC paths, and absolute or home-relative POSIX paths. A path
# may contain spaces (show names, "Jane Doe"), so it runs to the end of the
# line or a quote; only its last part survives.
_WIN_PATH = re.compile(r"(?<![\w/\\])(?:[A-Za-z]:[\\/]|\\\\[^\\\s'\"<>]+\\)[^'\"<>\r\n]*")
_POSIX_PATH = re.compile(r"(?<![\w.:/\\~])~?/(?:[^/'\"<>\r\n]+/)+[^/'\"<>\r\n]*")


def file_name(path: str | os.PathLike) -> str:
    """The last part of a Windows or POSIX path; never the folders above it."""
    text = str(path).rstrip("\\/ ")
    name = PureWindowsPath(text).name if ("\\" in text or ":" in text[:3]) else PurePosixPath(text).name
    return name or "<path>"


def host(url: str) -> str:
    """The host of a URL: no user, password, port, path or query."""
    try:
        return urlsplit(url).hostname or "<no host>"
    except ValueError:
        return "<bad url>"


def source(url_or_path: str | os.PathLike) -> str:
    """What a log line may say about where something came from: the host of a
    URL, or the file name of a local path."""
    text = str(url_or_path)
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", text):
        if text.lower().startswith("file:"):
            return file_name(urlsplit(text).path)
        return host(text)
    return file_name(text)


def redact(text: object) -> str:
    """Reduce every URL to scheme://host/... and every local path to its file name."""

    def _url(m: re.Match[str]) -> str:
        raw = m.group(0)
        if raw.lower().startswith("file:"):
            return file_name(urlsplit(raw).path)
        return f"{raw.split(':', 1)[0]}://{host(raw)}/..."

    out = _URL.sub(_url, str(text))
    out = _WIN_PATH.sub(lambda m: file_name(m.group(0)), out)
    return _POSIX_PATH.sub(lambda m: file_name(m.group(0)), out)


def safe_exception(exc_info) -> str:
    """An exception as error class, redacted message and frames by file name only."""
    etype, value, tb = exc_info
    if etype is None:
        return ""
    frames = traceback.extract_tb(tb)[-8:] if tb is not None else []
    lines = ["Traceback (file names only):"]
    lines += [f"  {file_name(f.filename)}:{f.lineno} in {f.name}" for f in frames]
    message = redact(value) if value is not None and str(value) else ""
    lines.append(f"{etype.__name__}: {message}" if message else etype.__name__)
    return "\n".join(lines)


class _RunIdFilter(logging.Filter):
    def __init__(self, run_id: str) -> None:
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = self.run_id
        return True


class _SafeTextFormatter(logging.Formatter):
    """Text lines with the message and any exception redacted. Never reuses a
    record's cached exc_text, which another handler may have filled unredacted."""

    def format(self, record: logging.LogRecord) -> str:
        record.message = redact(record.getMessage())
        record.asctime = self.formatTime(record, self.datefmt)
        line = self.formatMessage(record)
        if record.exc_info:
            line += "\n" + safe_exception(record.exc_info)
        return line


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "run_id": getattr(record, "run_id", None),
            "msg": redact(record.getMessage()),
        }
        if record.exc_info:
            out["exc"] = safe_exception(record.exc_info)
        return json.dumps(out, ensure_ascii=False)


class _StderrHandler(logging.Handler):
    """Writes to whatever sys.stderr is at emit time.

    The packaged window app runs with sys.stderr set to None, and tests swap
    sys.stderr per test, so the stream is looked up per line, never stored.
    """

    def emit(self, record: logging.LogRecord) -> None:
        stream = sys.stderr
        if stream is None:
            return
        try:
            stream.write(self.format(record) + "\n")
            stream.flush()
        except Exception:
            self.handleError(record)


def run_id() -> str | None:
    """This process's run id, or None before setup()."""
    return _run_id


def setup(log_file: Path | None = None) -> str:
    """Configure the root logger once and return this run's id.

    Later calls return the same id and change nothing, so every entry point
    can call it without knowing whether another one already has.
    """
    global _run_id
    if _run_id is not None:
        return _run_id
    _run_id = uuid.uuid4().hex[:12]

    level_name = os.environ.get("LOG_LEVEL", "WARNING").strip().upper()
    level = logging.getLevelName(level_name)
    if not isinstance(level, int):
        level = logging.WARNING
    use_json = os.environ.get("LOG_FORMAT", "text").strip().lower() == "json"
    formatter: logging.Formatter = _JsonFormatter() if use_json else _SafeTextFormatter(TEXT_FORMAT)

    handlers: list[logging.Handler] = [_StderrHandler()]
    if log_file is not None:
        try:
            handlers.append(
                logging.handlers.RotatingFileHandler(
                    log_file,
                    maxBytes=LOG_FILE_MAX_BYTES,
                    backupCount=LOG_FILE_BACKUPS,
                    encoding="utf-8",
                    delay=True,
                )
            )
        except OSError:
            pass  # an unwritable state folder must not stop the app
    root = logging.getLogger()
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(_RunIdFilter(_run_id))
        root.addHandler(handler)
        _handlers.append(handler)
    root.setLevel(level)
    return _run_id


def reset() -> None:
    """Undo setup() (tests only)."""
    global _run_id
    root = logging.getLogger()
    for handler in _handlers:
        root.removeHandler(handler)
        handler.close()
    _handlers.clear()
    _run_id = None
