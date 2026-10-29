"""app.run_training checks the deck theme before the paid call.

Regression: the store default was ``baek``, a theme that exists only with the
optional private engine, so in a public checkout Generate Training (and
Auto-train) paid for a deck and then failed to render it. No network, no
spend: the key lookup and ``generate_training`` are stubbed.
"""

from __future__ import annotations

import pytest


def test_default_theme_is_renderable(app_mod):
    import deck_render

    assert app_mod.DEFAULT_SETTINGS["deck_theme"] in deck_render.THEMES


def test_unknown_theme_fails_before_the_paid_call(app_mod, monkeypatch, tmp_path):
    import training as tr

    calls = []
    monkeypatch.setattr(app_mod, "anthropic_api_key", lambda: "not-a-real-key")
    monkeypatch.setattr(tr, "generate_training", lambda **kw: calls.append(kw))
    transcript = tmp_path / "t.txt"
    transcript.write_text("A short transcript.", encoding="utf-8")
    with pytest.raises(app_mod.TrainingError, match="isn't available"):
        app_mod.run_training(
            {"name": "Show"},
            {"date": "2026-10-28", "title": "Ep"},
            transcript,
            {"deck_theme": "no-such-theme"},
        )
    assert calls == []
