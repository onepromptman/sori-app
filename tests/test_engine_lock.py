"""One engine per state folder: the browser app, the window and the sweep share one lock.

Nothing here may open a window or a dialog: the window toolkit is replaced by a
stub that fails the test if it is asked to draw, and the message box by a list.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

import app
import webserver
from engine_lock import LOCK_NAME, EngineLock

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def told(monkeypatch) -> list[str]:
    messages: list[str] = []
    monkeypatch.setattr(webserver, "_tell_user", messages.append)
    return messages


@pytest.fixture
def no_window(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to open a window")

    fake = types.SimpleNamespace(create_window=refuse, start=refuse)
    monkeypatch.setitem(sys.modules, "webview", fake)
    return fake


def free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_a_second_engine_is_refused_until_the_first_lets_go(sori_home):
    first, second = EngineLock(sori_home), EngineLock(sori_home)
    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True
    second.release()
    assert (sori_home / LOCK_NAME).exists()


def test_each_state_folder_has_its_own_lock(sori_home, tmp_path):
    with EngineLock(sori_home) as one, EngineLock(tmp_path) as two:
        assert one and two


def test_two_sweeps_cannot_run_together(sori_home, monkeypatch):
    """Regression: the sweep only looked for the browser app, so a second sweep
    started beside a slow first one and queued the same episodes again."""
    monkeypatch.setattr(app, "check_all", lambda: pytest.fail("a second sweep checked feeds"))
    app.save_store({**app.load_store(), "shows": [{"id": "s", "name": "Show", "type": "rss"}]})
    with EngineLock(sori_home):
        assert app.sweep() == 0
    assert "This sweep did nothing" in (sori_home / "sweep.log").read_text(encoding="utf-8")


def test_a_finished_sweep_lets_go_of_the_lock(sori_home):
    assert app.sweep() == 0  # no shows: returns early, and must still release
    with EngineLock(sori_home) as free:
        assert free


def test_the_window_stands_down_while_another_engine_runs(sori_home, told, no_window):
    """Regression: --window had no guard at all."""
    with EngineLock(sori_home):
        assert app.run_window() == 1
    assert "already running" in told[0]


def test_the_browser_app_stands_down_while_a_sweep_runs(sori_home, told, monkeypatch):
    monkeypatch.setattr(webserver.webbrowser, "open", lambda url: pytest.fail("opened a browser"))
    started = []
    with EngineLock(sori_home):
        code = webserver.run(app.Api(), ROOT / "ui", sori_home, lambda: started.append(1), port=free_port())
    assert code == 1
    assert started == []
    assert told == [webserver.BUSY_MESSAGE]


def test_a_failed_start_does_not_keep_the_lock(sori_home, told):
    import socket

    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        code = webserver.run(app.Api(), ROOT / "ui", sori_home, lambda: None, port=other.getsockname()[1])
    assert code == 1
    with EngineLock(sori_home) as free:
        assert free
