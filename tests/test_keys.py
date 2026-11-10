"""Where the paid key may come from, and the opt-in that gates the environment."""

from __future__ import annotations

import json

import app


def test_env_key_ignored_without_opt_in(monkeypatch, tmp_path):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-env-0000")
    monkeypatch.delenv("SORI_KEY_FROM_ENV", raising=False)
    assert app.anthropic_api_key() is None


def test_env_key_used_with_opt_in(monkeypatch, tmp_path):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "  fixture-env-0000 ")
    monkeypatch.setenv("SORI_KEY_FROM_ENV", "1")
    assert app.anthropic_api_key() == "fixture-env-0000"
    monkeypatch.setenv("SORI_KEY_FROM_ENV", "yes")  # only the literal "1" opts in
    assert app.anthropic_api_key() is None


def test_saved_key_wins_over_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    (tmp_path / "credentials.json").write_text(json.dumps({"anthropic_api_key": "fixture-saved-1111"}))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-env-0000")
    monkeypatch.setenv("SORI_KEY_FROM_ENV", "1")
    assert app.anthropic_api_key() == "fixture-saved-1111"
