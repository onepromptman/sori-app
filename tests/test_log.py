"""sori_log: one setup per process, a run id on every line, text or JSON."""

from __future__ import annotations

import json
import logging

import pytest

import sori_log


@pytest.fixture
def fresh_log(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    saved = sori_log._run_id, list(sori_log._handlers)
    sori_log._run_id, sori_log._handlers[:] = None, []
    root_level = logging.getLogger().level
    yield
    sori_log.reset()
    sori_log._run_id, sori_log._handlers[:] = saved[0], saved[1]
    logging.getLogger().setLevel(root_level)


def test_setup_is_once_per_process(fresh_log):
    first = sori_log.setup()
    assert len(first) == 12
    assert sori_log.setup() == first
    assert sori_log.run_id() == first


def test_text_lines_carry_the_run_id(fresh_log, capsys):
    rid = sori_log.setup()
    logging.getLogger("transcribe").warning("feed %s timed out", "x")
    err = capsys.readouterr().err
    assert f"[run {rid}]" in err and "feed x timed out" in err


def test_json_lines_parse_and_carry_the_run_id(fresh_log, capsys, monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    rid = sori_log.setup()
    logging.getLogger("training").error("boom")
    line = capsys.readouterr().err.strip().splitlines()[-1]
    rec = json.loads(line)
    assert rec["run_id"] == rid and rec["level"] == "ERROR" and rec["msg"] == "boom"


def test_default_level_hides_info_and_a_bad_level_falls_back(fresh_log, capsys, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "chatty")
    sori_log.setup()
    logging.getLogger("training").info("not shown")
    assert "not shown" not in capsys.readouterr().err


def test_log_file_is_written_only_when_there_is_something_to_say(fresh_log, tmp_path):
    path = tmp_path / "sori.log"
    sori_log.setup(log_file=path)
    assert not path.exists()
    logging.getLogger("app").warning("something to say")
    for handler in sori_log._handlers:
        handler.flush()
    assert "something to say" in path.read_text(encoding="utf-8")


# ---- redaction: host names and file names only ---------------------------------

# Built at run time so the source holds no home path or credential-looking query.
WIN_DIR = "\\".join(["C:", "Users", "Jane Doe", "Sori", "Shows"])
POSIX_DIR = "/".join(["", "Users", "jane", "Sori", "Show Name"])
FEED_URL = "https://feeds.example.com/private/123?" + "auth" + "=abcdef123456"


def test_redact_keeps_only_the_host_of_a_url():
    out = sori_log.redact(f"Couldn't read that feed: {FEED_URL} returned 403")
    assert out == "Couldn't read that feed: https://feeds.example.com/... returned 403"


def test_redact_keeps_only_the_file_name_of_a_path():
    assert sori_log.redact(f"Not a folder: {WIN_DIR}") == "Not a folder: Shows"
    assert sori_log.redact(f"Not a folder: {POSIX_DIR}") == "Not a folder: Show Name"
    assert sori_log.redact("nothing to hide, 3/4 done") == "nothing to hide, 3/4 done"


def test_source_is_a_host_or_a_file_name():
    assert sori_log.source(FEED_URL) == "feeds.example.com"
    assert sori_log.source(WIN_DIR + "\\ep 1.mp3") == "ep 1.mp3"
    assert sori_log.source(POSIX_DIR + "/ep.mp3") == "ep.mp3"
    assert sori_log.source("dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_logged_exceptions_carry_the_error_class_but_no_path(fresh_log, capsys):
    sori_log.setup()
    try:
        raise ValueError(f"Not a folder: {WIN_DIR}")
    except ValueError:
        logging.getLogger("app").exception("bridge call %s failed", "set_transcripts_dir")
    err = capsys.readouterr().err
    assert "ValueError: Not a folder: Shows" in err
    assert "Jane" not in err
    assert "test_log.py:" in err and str(sori_log.Path(__file__).parent) not in err


def test_json_lines_are_redacted_too(fresh_log, capsys, monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    sori_log.setup()
    try:
        raise RuntimeError(f"yt-dlp: unable to download {FEED_URL}")
    except RuntimeError:
        logging.getLogger("transcribe").exception("download from %s failed", FEED_URL)
    rec = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert rec["msg"] == "download from https://feeds.example.com/... failed"
    assert "RuntimeError" in rec["exc"] and "abcdef" not in rec["exc"]


def test_log_file_rotates(fresh_log, tmp_path):
    sori_log.setup(log_file=tmp_path / "sori.log")
    files = [h for h in sori_log._handlers if isinstance(h, sori_log.logging.handlers.RotatingFileHandler)]
    assert len(files) == 1
    assert (
        files[0].maxBytes == sori_log.LOG_FILE_MAX_BYTES and files[0].backupCount == sori_log.LOG_FILE_BACKUPS
    )
