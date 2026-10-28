"""settings.py: the Settings pane from the CLI, same store as the window.

Runs ``settings.main(argv)`` in-process under ``sori_home``. The API key
tests plant a fake key in the environment and assert that nothing beyond its
last four characters ever reaches stdout or stderr, and that it lands in
credentials.json, never in shows.json.
"""
from __future__ import annotations

import json

import pytest

FAKE_KEY = "sk-ant-test-0123456789abcdefXYZ9"


@pytest.fixture
def settings(app_mod):
    import settings
    return settings


def _run(settings, capsys, argv):
    code = settings.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def _snap(settings, capsys) -> dict:
    code, out, _ = _run(settings, capsys, ["show", "--json"])
    assert code == 0
    return json.loads(out)


# -- show ------------------------------------------------------------------------

def test_show_defaults(settings, sori_home, capsys):
    code, out, err = _run(settings, capsys, ["show"])
    assert code == 0 and err == ""
    assert "model           base.en" in out
    assert "lang            en" in out
    assert "deck_theme      studio" in out
    assert "api key         not set" in out
    assert str(sori_home / "Transcripts") in out
    assert "tokens.css" not in out  # deck_render's import warning stays out of CLI output

    snap = _snap(settings, capsys)
    assert snap == {
        "model": "base.en", "lang": "en",
        "transcripts_dir": str(sori_home / "Transcripts"),
        "deck_theme": "studio", "api_key_set": False, "api_key_last4": None,
    }


# -- model / lang / deck-theme -----------------------------------------------------

def test_model_and_lang_persist(settings, app_mod, capsys):
    code, out, _ = _run(settings, capsys, ["model", "small.en"])
    assert code == 0 and out.strip() == "model small.en"
    code, out, _ = _run(settings, capsys, ["lang", "auto"])
    assert code == 0 and out.strip() == "lang auto"
    snap = _snap(settings, capsys)
    assert snap["model"] == "small.en" and snap["lang"] == "auto"
    # Parity: the window's bridge reads the same values.
    data = app_mod.Api().get_settings()["data"]
    assert data["model"] == "small.en" and data["lang"] == "auto"


def test_invalid_model_and_lang_are_usage_errors(settings, capsys):
    code, _, err = _run(settings, capsys, ["model", "medium.en"])
    assert code == 2 and "invalid choice" in err
    assert _run(settings, capsys, ["lang", "fr"])[0] == 2
    assert _run(settings, capsys, ["deck-theme", "neon"])[0] == 2


def test_korean_with_english_model_is_engine_refusal(settings, capsys):
    code, out, err = _run(settings, capsys, ["lang", "ko"])
    assert code == 1 and out == ""
    assert err.startswith("!! ") and "large-v3" in err
    assert "Traceback" not in err
    assert _snap(settings, capsys)["lang"] == "en"

    assert _run(settings, capsys, ["model", "large-v3"])[0] == 0
    assert _run(settings, capsys, ["lang", "ko"])[0] == 0
    # And back the other way: ko is set, so an .en model is refused.
    code, _, err = _run(settings, capsys, ["model", "tiny.en"])
    assert code == 1 and err.startswith("!! ")
    assert _snap(settings, capsys)["model"] == "large-v3"


def test_deck_theme_persists(settings, app_mod, capsys):
    # Not a hardcoded name: the branded themes only exist where engine/ does,
    # so naming one here fails the suite on a public clone for a reason that
    # has nothing to do with what this test checks.
    import deck_render
    theme = sorted(deck_render.THEMES)[-1]
    code, out, _ = _run(settings, capsys, ["deck-theme", theme])
    assert code == 0 and out.strip() == f"deck-theme {theme}"
    assert _snap(settings, capsys)["deck_theme"] == theme
    assert app_mod.Api().get_training_settings()["data"]["deck_theme"] == theme


# -- transcripts-dir ---------------------------------------------------------------

def test_transcripts_dir_set_and_default(settings, app_mod, sori_home, tmp_path, capsys):
    target = tmp_path / "elsewhere" / "Transcripts"
    assert not target.exists()
    code, out, _ = _run(settings, capsys, ["transcripts-dir", str(target)])
    assert code == 0
    assert out.strip() == f"transcripts_dir {target.resolve()}"
    assert target.is_dir()
    assert app_mod.transcripts_dir() == target.resolve()
    assert _snap(settings, capsys)["transcripts_dir"] == str(target.resolve())
    store = json.loads((sori_home / "shows.json").read_text(encoding="utf-8"))
    assert store["settings"]["transcripts_dir"] == str(target.resolve())

    code, out, _ = _run(settings, capsys, ["transcripts-dir", "--default"])
    assert code == 0 and out.strip() == f"transcripts_dir {sori_home / 'Transcripts'}"
    assert app_mod.transcripts_dir() == sori_home / "Transcripts"
    store = json.loads((sori_home / "shows.json").read_text(encoding="utf-8"))
    assert store["settings"]["transcripts_dir"] is None


def test_transcripts_dir_refuses_a_file(settings, tmp_path, capsys):
    f = tmp_path / "afile.txt"
    f.write_text("x", encoding="utf-8")
    code, _, err = _run(settings, capsys, ["transcripts-dir", str(f)])
    assert code == 1 and err.startswith("!! ")


def test_transcripts_dir_needs_exactly_one_of_path_or_default(settings, tmp_path, capsys):
    assert _run(settings, capsys, ["transcripts-dir"])[0] == 2
    assert _run(settings, capsys, ["transcripts-dir", str(tmp_path), "--default"])[0] == 2


# -- api-key -----------------------------------------------------------------------

def test_api_key_set_from_env_prints_only_last4(settings, sori_home, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    code, out, err = _run(settings, capsys, ["api-key", "set"])
    assert code == 0
    assert out.strip() == f"saved (...{FAKE_KEY[-4:]})"
    assert FAKE_KEY not in out and FAKE_KEY not in err
    assert FAKE_KEY[:-4] not in out  # nothing beyond the last 4, anywhere

    creds = json.loads((sori_home / "credentials.json").read_text(encoding="utf-8"))
    assert creds["anthropic_api_key"] == FAKE_KEY
    shows_json = sori_home / "shows.json"
    assert not shows_json.exists() or FAKE_KEY not in shows_json.read_text(encoding="utf-8")

    code, out, _ = _run(settings, capsys, ["api-key", "status"])
    assert code == 0 and out.strip() == f"api key: set (...{FAKE_KEY[-4:]})"
    snap = _snap(settings, capsys)
    assert snap["api_key_set"] is True and snap["api_key_last4"] == FAKE_KEY[-4:]
    assert FAKE_KEY not in json.dumps(snap)


def test_api_key_never_taken_from_argv(settings, capsys):
    # Extra positional = argparse usage error, and the key is not saved.
    assert _run(settings, capsys, ["api-key", "set", FAKE_KEY])[0] == 2
    assert _run(settings, capsys, ["api-key", "status"])[1].strip() == "api key: not set"


def test_api_key_set_without_env_is_exit_1(settings, capsys):
    code, out, err = _run(settings, capsys, ["api-key", "set"])
    assert code == 1 and out == ""
    assert err.startswith("!! ") and "ANTHROPIC_API_KEY" in err


def test_api_key_clear(settings, app_mod, sori_home, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    assert _run(settings, capsys, ["api-key", "set"])[0] == 0
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    code, out, _ = _run(settings, capsys, ["api-key", "clear"])
    assert code == 0 and out.strip() == "cleared"
    assert _run(settings, capsys, ["api-key", "status"])[1].strip() == "api key: not set"
    assert app_mod.anthropic_api_key() is None
    assert "anthropic_api_key" not in json.loads(
        (sori_home / "credentials.json").read_text(encoding="utf-8"))


# -- usage -------------------------------------------------------------------------

def test_usage_errors_are_exit_2(settings, capsys):
    assert _run(settings, capsys, [])[0] == 2
    assert _run(settings, capsys, ["bogus"])[0] == 2
    assert _run(settings, capsys, ["model"])[0] == 2
    assert _run(settings, capsys, ["api-key", "rotate"])[0] == 2
    assert _run(settings, capsys, ["--help"])[0] == 0
