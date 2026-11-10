"""preflight.py: the one script every skill runs before it touches Sori.

No test here creates a real environment or reaches the network: the two
commands preflight runs (`python -m venv` and `pip install`) are replaced by a
recorder that fakes their effect.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

import preflight

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("shows", "sweep", "train", "transcribe")


@pytest.fixture
def runs(sori_home, monkeypatch):
    """Record the commands preflight runs; `runs.fail` makes pip fail with that text."""
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)

    class Recorder(list):
        fail = ""

    calls = Recorder()

    def fake_run(command, log):
        calls.append(command)
        if command[1:3] == ["-m", "venv"]:
            python = preflight.venv_python(Path(command[3]))
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")
            return 0, ""
        return (1, calls.fail) if calls.fail else (0, "")

    monkeypatch.setattr(preflight, "_run", fake_run)
    return calls


def test_an_old_python_gets_one_plain_sentence():
    with pytest.raises(preflight.NotReady) as stop:
        preflight.check_python((3, 10, 12))
    assert "Python 3.11 or newer" in str(stop.value) and "3.10" in str(stop.value)
    preflight.check_python((3, 11, 0))


def test_the_floor_matches_pyproject():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    floor = ".".join(str(n) for n in preflight.PYTHON_FLOOR)
    assert project["requires-python"] == f">={floor}"


def test_each_verb_installs_only_its_own_exact_pins(runs):
    assert preflight.main(["train"]) == 0
    install = runs[-1]
    assert [a for a in install if "==" in a] == [f"python-pptx=={preflight.pins()['python-pptx']}"]
    assert not any("whisper" in a or "anthropic" in a for a in install)


def test_what_the_pins_pull_in_is_held_to_the_lock(runs):
    """Regression: with only the direct pins, pip took the newest av, which the
    pinned faster-whisper cannot call, and every transcription failed."""
    preflight.main(["transcribe"])
    install = runs[-1]
    assert install[install.index("--constraint") + 1] == str(ROOT / "requirements.lock")
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    assert re.search(r"^av==", lock, re.M) and re.search(r"^ctranslate2==", lock, re.M)


def test_every_needed_package_is_pinned_in_pyproject():
    every = preflight.pins()
    for verb in preflight.NEEDS:
        assert set(preflight.wanted(verb, api=True)) <= set(every)


def test_a_second_run_touches_nothing(runs, capsys):
    assert preflight.main(["transcribe"]) == 0
    first = len(runs)
    assert preflight.main(["transcribe"]) == 0
    assert len(runs) == first
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("SORI_PY=")


def test_a_later_verb_adds_only_what_is_missing(runs):
    preflight.main(["train"])
    preflight.main(["shows"])
    assert [a.split("==")[0] for a in runs[-1] if "==" in a] == ["yt-dlp"]


def test_the_environment_lives_in_the_sori_folder(runs, sori_home):
    preflight.main(["train"])
    assert preflight.venv_dir() == sori_home / "venv"
    assert json.loads((sori_home / "venv" / preflight.MARKER).read_text(encoding="utf-8"))["pins"]


def test_claude_plugin_data_wins_when_set(runs, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "data"))
    assert preflight.venv_dir() == tmp_path / "data" / "venv"


def test_a_refused_install_is_one_sentence_naming_the_way_out(runs, capsys):
    runs.fail = "ERROR: Could not find a version that satisfies the requirement yt-dlp\nProxyError(403)"
    assert preflight.main(["transcribe"]) == 2
    captured = capsys.readouterr()
    assert captured.err.strip() == f"!! {preflight.REFUSED}"
    assert "SORI_PY" not in captured.out
    assert "network access" in preflight.REFUSED and "Claude Code on your own computer" in preflight.REFUSED


def test_a_failed_install_is_not_recorded_as_done(runs):
    runs.fail = "error: something else broke"
    assert preflight.main(["train"]) == 2
    runs.fail = ""
    before = len(runs)
    assert preflight.main(["train"]) == 0
    assert len(runs) == before + 1 and "pip" in runs[-1]


def test_the_whisper_download_is_announced_before_it_happens(runs, monkeypatch, capsys):
    import transcribe

    monkeypatch.setattr(transcribe, "whisper_model_is_cached", lambda model, device="cpu": False)
    preflight.main(["transcribe"])
    assert "download the Whisper model base.en" in capsys.readouterr().out
    monkeypatch.setattr(transcribe, "whisper_model_is_cached", lambda model, device="cpu": True)
    preflight.main(["transcribe"])
    assert "Whisper model" not in capsys.readouterr().out


def test_a_missing_javascript_runtime_is_mentioned_for_youtube_verbs(runs, monkeypatch, capsys):
    monkeypatch.setattr(preflight.shutil, "which", lambda name: None)
    preflight.main(["shows"])
    assert "Deno" in capsys.readouterr().out
    preflight.main(["train"])
    assert "Deno" not in capsys.readouterr().out


def test_old_data_folder_is_moved_not_hidden(tmp_path, monkeypatch):
    """Creating an empty Sori folder first would stop the app adopting PodcastStudio."""
    monkeypatch.delenv("SORI_HOME", raising=False)
    monkeypatch.delenv("PODCAST_STUDIO_HOME", raising=False)
    monkeypatch.setattr(preflight.Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / "PodcastStudio").mkdir()
    (tmp_path / "PodcastStudio" / "shows.json").write_text("{}", encoding="utf-8")
    assert preflight.sori_home() == tmp_path / "Sori"
    assert (tmp_path / "Sori" / "shows.json").exists()


@pytest.mark.parametrize("skill", SKILLS)
def test_every_skill_runs_the_preflight_first(skill):
    text = (ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    assert f'preflight.py" {skill}' in text
    assert "pip install" not in text, "skills never tell the session to run pip by hand"
    first_command = re.search(r"```bash\n(.+)", text).group(1)
    assert "preflight.py" in first_command


def test_manifest_descriptions_fit_the_upload_limit_and_versions_agree():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    entry = market["plugins"][0]
    for description in (plugin["description"], market["description"], entry["description"]):
        assert len(description) <= 500
    assert plugin["version"] == entry["version"] == project["version"]
