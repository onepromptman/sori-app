"""Where the paid key may come from, and the opt-in that gates the environment."""
from __future__ import annotations

import json

import app


def test_env_key_ignored_without_opt_in(monkeypatch, tmp_path):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-0000")
    monkeypatch.delenv("SORI_KEY_FROM_ENV", raising=False)
    assert app.anthropic_api_key() is None


def test_env_key_used_with_opt_in(monkeypatch, tmp_path):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "  sk-ant-env-0000 ")
    monkeypatch.setenv("SORI_KEY_FROM_ENV", "1")
    assert app.anthropic_api_key() == "sk-ant-env-0000"
    monkeypatch.setenv("SORI_KEY_FROM_ENV", "yes")       # only the literal "1" opts in
    assert app.anthropic_api_key() is None


def test_saved_key_wins_over_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    (tmp_path / "credentials.json").write_text(json.dumps({"anthropic_api_key": "sk-ant-saved-1111"}))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-0000")
    monkeypatch.setenv("SORI_KEY_FROM_ENV", "1")
    assert app.anthropic_api_key() == "sk-ant-saved-1111"


def test_training_falls_back_to_a_theme_this_checkout_has(monkeypatch, tmp_path):
    """A store written by the exe says deck_theme=baek; a public checkout only
    has studio. Rendering must not fail after the paid call succeeded."""
    import deck_render
    import training as tr
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    (tmp_path / "credentials.json").write_text(json.dumps({"anthropic_api_key": "sk-ant-saved-1111"}))
    transcript = tmp_path / "t.txt"
    transcript.write_text("Title\nShow — 2026-01-01\nhttp://x\n\nhello world " * 20)
    outline = {"deck_title": "T", "study_guide_markdown": "# g",
               "slides": [{"kind": "content", "heading": f"h{i}", "points": [{"label": "p"}]} for i in range(6)]}
    monkeypatch.setattr(tr, "generate_training",
                        lambda **kw: tr.result_from_outline(outline, kw["meta"]))
    seen = {}
    real = deck_render.render_pptx

    def spy(outline_, theme, path):
        seen["theme"] = theme
        return real(outline_, theme, path)

    monkeypatch.setattr(deck_render, "render_pptx", spy)
    show = {"id": "s", "name": "Show"}
    episode = {"id": "e", "title": "Ep", "date": "2026-01-01"}
    pptx, md = app.run_training(show, episode, transcript, {"deck_theme": "not-a-theme"})
    assert pptx.exists() and md.exists()
    assert seen["theme"] in deck_render.THEMES
