"""Shared pytest fixtures for Sori.

Two guarantees every test inherits:

* **Isolation.** ``SORI_HOME`` points at a fresh temp dir before ``app`` is
  imported and again per test, so nothing here can touch Bryan's real
  ``%USERPROFILE%\Sori``.
* **No spend.** A fake ``anthropic`` module is installed in ``sys.modules``
  before any test runs. Its ``Anthropic`` client raises on construction, so a
  test that reaches the real API path fails loudly instead of billing. Tests
  that need a working client replace ``fake_anthropic.Anthropic`` explicitly.
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Before any module under test is imported.
os.environ["SORI_HOME"] = tempfile.mkdtemp(prefix="sori-pytest-")
os.environ.pop("PODCAST_STUDIO_HOME", None)
os.environ.pop("ANTHROPIC_API_KEY", None)


class SpendGuard(RuntimeError):
    """Raised when a test would have made a real Claude API call."""


def _make_fake_anthropic() -> types.ModuleType:
    mod = types.ModuleType("anthropic")

    class APIError(Exception):
        pass

    class AuthenticationError(APIError):
        pass

    class Anthropic:
        def __init__(self, *args, **kwargs):
            raise SpendGuard("a test tried to construct a real Anthropic client")

    mod.APIError = APIError
    mod.AuthenticationError = AuthenticationError
    mod.Anthropic = Anthropic
    mod.__sori_fake__ = True
    return mod


fake_anthropic = _make_fake_anthropic()
sys.modules["anthropic"] = fake_anthropic


@pytest.fixture
def sori_home(tmp_path, monkeypatch) -> Path:
    """A fresh, empty state dir; ``SORI_HOME`` points at it for the test."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("SORI_HOME", str(home))
    monkeypatch.delenv("PODCAST_STUDIO_HOME", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return home


@pytest.fixture
def app_mod(sori_home):
    """The ``app`` module, imported after ``SORI_HOME`` is isolated."""
    import app
    return app


EPISODES = [
    {"id": f"e{i}", "title": f"Episode {i}", "url": f"https://x/{i}", "kind": "youtube",
     "date": f"2026-09-0{i}"}
    for i in range(1, 8)
]


@pytest.fixture
def fake_feed(app_mod, monkeypatch):
    """Replace the network feed parser. Returns a setter: ``fake_feed(name, episodes)``."""
    state = {"name": "Fake Show", "episodes": list(EPISODES)}

    def parse(feed_url, kind):
        return state["name"], list(state["episodes"])

    monkeypatch.setattr(app_mod, "parse_feed", parse)

    def set_feed(name="Fake Show", episodes=None):
        state["name"] = name
        state["episodes"] = list(EPISODES if episodes is None else episodes)

    return set_feed


@pytest.fixture
def fake_transcriber(app_mod, monkeypatch):
    """Replace Whisper/yt-dlp with a cancellable fake that writes a stub file.

    Returns the list of episode ids it produced, in order. Each run takes about
    ``fake_transcriber.seconds`` (default 2 s) and honours ``cancel``.
    """
    import time

    made: list[str] = []
    made_attr = types.SimpleNamespace(seconds=2.0)

    def run(show, episode, settings, on_progress=None, cancel=None):
        steps = max(int(made_attr.seconds / 0.05), 1)
        for _ in range(steps):
            if cancel is not None and cancel.is_set():
                raise app_mod.tx.TranscriptionCancelled()
            time.sleep(0.05)
        p = app_mod.transcripts_dir() / show["name"] / f"{episode['id']}.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("fake", encoding="utf-8")
        made.append(episode["id"])
        return p

    monkeypatch.setattr(app_mod, "run_transcription", run)
    made_attr.made = made
    return made_attr


@pytest.fixture
def seeded_show(app_mod):
    """One subscribed, auto-on RSS show with an empty ``seen`` list."""
    data = app_mod.load_store()
    show = {"id": "s1", "name": "Fake Show", "type": "rss", "feed_url": "https://x/feed",
            "source_url": "https://x/feed", "auto": True,
            "added_at": "2026-09-05T00:00:00+00:00", "last_seen": None,
            "last_checked": None, "seen": [], "folder": "unsorted"}
    data["shows"].append(show)
    app_mod.save_store(data)
    return show
