import argparse
import json

import pytest

import sori
from pipeline import brief, design, ledger


def test_reused_feed_ids_do_not_mix_learning_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    ledger.record("First show", "episode-1", "transcribed", "test")
    ledger.record("Second show", "episode-1", "reviewed", "test")
    pending = ledger.awaiting("transcribed", "triaged")
    assert len(pending) == 1
    assert pending[0]["show"] == "First show"


def test_failed_episode_can_resume_without_poll_reset(tmp_path, monkeypatch):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    ledger.record("Show", "episode", "failed", "test")
    ledger.record("Show", "episode", "discovered", "poll")
    assert ledger.summary()["failed"] == 1
    ledger.record("Show", "episode", "transcribed", "retry")
    assert ledger.summary()["failed"] == 0
    assert ledger.summary()["transcribed"] == 1


def test_ledger_ignores_non_object_json_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    ledger.ledger_path().write_text("null\n[]\n42\n", encoding="utf-8")
    ledger.record("Show", "episode", "transcribed", "test")
    assert len(ledger.latest()) == 1


def test_rejected_source_quote_is_not_in_diagnostics():
    source_fragment = "fictional restricted excerpt for redaction test"
    text = brief.TEMPLATE.format(title="Demo", show="Show", date="", source="")
    text = text.replace("exact words from the transcript", source_fragment)
    result = brief.check(text, "A different source.")
    assert not result.ok
    assert source_fragment not in str(result)


def test_launcher_refreshes_pins_without_unbounded_upgrade(monkeypatch):
    calls = []
    monkeypatch.setattr(sori, "ensure_env", lambda profile, force: calls.append((profile, force)) or 0)
    assert sori.cmd_update(argparse.Namespace(profile="claude")) == 0
    assert calls == [("claude", True)]


def test_changed_lock_invalidates_optional_launcher_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(sori, "ROOT", tmp_path)
    for name in ["requirements-claude.txt", "requirements.txt", "requirements.lock", "pyproject.toml"]:
        (tmp_path / name).write_text("first\n", encoding="utf-8")
    before = sori._fingerprint(["requirements-claude.txt"])
    (tmp_path / "requirements.lock").write_text("second\n", encoding="utf-8")
    assert before != sori._fingerprint(["requirements-claude.txt"])


@pytest.mark.parametrize("value", [None, [], 7])
def test_non_object_pipeline_settings_use_defaults(tmp_path, monkeypatch, value):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    design.config_path().write_text(json.dumps(value), encoding="utf-8")
    assert design.load_config() == design.DEFAULTS


def test_manual_handoffs_never_execute_external_tools(tmp_path, monkeypatch):
    # This is a behavioral boundary: pipeline commands may write files but
    # should not call a shell or an external slide provider.
    import subprocess
    from test_pipeline import GOOD_BRIEF, TRANSCRIPT

    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("unexpected external execution"))
    episode = ledger.episode_dir("Show", {"id": "sample", "title": "Demo"})
    (episode / "brief.md").write_text(GOOD_BRIEF, encoding="utf-8")
    (episode / "transcript.txt").write_text(TRANSCRIPT, encoding="utf-8")
    for backend in design.BACKENDS:
        output = design.handoff(episode, backend)
        assert (output / "evidence.md").is_file()
        assert output.is_relative_to(episode)
