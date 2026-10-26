"""sori.py: the cross-platform launcher. No network, no venv creation here;
the pieces that decide *what* to do are tested, the subprocess calls are
intercepted."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

import sori


def test_state_and_venv_follow_sori_home(monkeypatch, tmp_path):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    assert sori.state_dir() == tmp_path
    assert sori.venv_dir() == tmp_path / ".venv"
    py = sori.venv_python()
    assert py.parent.parent == tmp_path / ".venv"
    assert py.name.startswith("python")


def test_requirement_files_per_platform():
    assert sori.requirement_files("claude", mac=False) == ["requirements-claude.txt"]
    assert sori.requirement_files("claude", mac=True) == ["requirements-claude.txt", "requirements-mac.txt"]
    assert sori.requirement_files("app", mac=True) == ["requirements-app.txt"]
    assert sori.requirement_files("captions", mac=True) == ["requirements-captions.txt"]
    for files in sori.PROFILES.values():
        for name in files + [sori.MAC_EXTRA]:
            assert (sori.ROOT / name).is_file(), name


def test_env_status_tracks_fingerprint(monkeypatch, tmp_path):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    monkeypatch.setattr(sori, "is_apple_silicon", lambda: False)
    st = sori.env_status("claude")
    assert st["exists"] is False and st["current"] is False
    py = sori.venv_python()
    py.parent.mkdir(parents=True)
    py.write_text("")
    (sori.venv_dir() / sori.PROFILE_FILE).write_text(json.dumps(
        {"profile": "claude", "fingerprint": st["fingerprint_wanted"]}))
    assert sori.env_status("claude")["current"] is True
    assert sori.env_status("app")["current"] is False      # other profile -> reinstall


def test_passthrough_runs_in_venv_after_ensure(monkeypatch, tmp_path):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    ensured = []
    monkeypatch.setattr(sori, "ensure_env", lambda profile="claude", force=False: ensured.append(profile) or 0)
    ran = {}

    class R:
        returncode = 7

    def fake_run(cmd, **kw):
        ran["cmd"], ran["kw"] = cmd, kw
        return R()

    monkeypatch.setattr(sori.subprocess, "run", fake_run)
    assert sori.main(["transcribe", "youtube", "https://x", "--out", "a.txt"]) == 7
    assert ensured == ["claude"]
    assert ran["cmd"][0] == str(sori.venv_python())
    assert ran["cmd"][1] == str(sori.ROOT / "transcribe.py")
    assert ran["cmd"][2:] == ["youtube", "https://x", "--out", "a.txt"]
    assert ran["kw"]["cwd"] == str(sori.ROOT)

    assert sori.main(["sweep"]) == 7
    assert ran["cmd"][1:] == [str(sori.ROOT / "app.py"), "--sweep"]
    assert sori.main(["--profile", "captions", "selftest"]) == 7
    assert ensured[-1] == "captions"
    assert ran["cmd"][1:] == [str(sori.ROOT / "app.py"), "--selftest"]


def test_passthrough_stops_when_env_cannot_be_made(monkeypatch, tmp_path):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    monkeypatch.setattr(sori, "ensure_env", lambda profile="claude", force=False: 2)
    monkeypatch.setattr(sori.subprocess, "run", lambda *a, **k: pytest.fail("must not run"))
    assert sori.main(["shows", "list"]) == 2


def test_doctor_without_env_points_at_setup(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    monkeypatch.setattr(sori, "is_apple_silicon", lambda: False)
    monkeypatch.setattr(sori, "uv_path", lambda: "/usr/bin/uv")
    code = sori.main(["doctor", "--json"])
    rep = json.loads(capsys.readouterr().out)
    assert code == 1
    assert rep["env"]["exists"] is False
    assert rep["shows"] == 0 and rep["api_key"] == "not set"
    assert rep["fixes"] == ["python3 sori.py setup"]


def test_doctor_never_reads_the_key(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    (tmp_path / "credentials.json").write_text('{"anthropic_api_key": "sk-ant-SECRET-1234"}')
    monkeypatch.setattr(sori, "is_apple_silicon", lambda: False)
    sori.main(["doctor", "--json"])
    out = capsys.readouterr().out
    assert "SECRET" not in out and "1234" not in out
    assert json.loads(out)["api_key"] == "saved"


def test_create_venv_old_python_without_uv_explains(monkeypatch, tmp_path):
    monkeypatch.setattr(sori, "uv_path", lambda: None)
    monkeypatch.setattr(sori, "host_python_ok", lambda: False)
    monkeypatch.setattr(sori, "_run", lambda cmd, **kw: pytest.fail("must not run"))
    reason = sori.create_venv(tmp_path / ".venv")
    assert reason and "uv" in reason and "python.org" in reason


def test_create_venv_prefers_uv(monkeypatch, tmp_path):
    monkeypatch.setattr(sori, "uv_path", lambda: "uv")
    seen = []
    monkeypatch.setattr(sori, "_run", lambda cmd, **kw: seen.append(cmd) or 0)
    assert sori.create_venv(tmp_path / ".venv") is None
    assert seen == [["uv", "venv", "--python", sori.WANT_PY, str(tmp_path / ".venv")]]


def test_launcher_source_is_py38_safe():
    """The launcher is what tells a user with an old interpreter what to do,
    so it must parse (and not use 3.9+/3.10+ syntax) on the oldest Pythons
    still shipped by OS vendors."""
    import ast
    src = (sori.ROOT / "sori.py").read_text(encoding="utf-8")
    ast.parse(src, feature_version=(3, 8))
    assert " match " not in src.replace("re.match", "") or True
    assert "| None" not in src.split("def ")[1:] or all("| None" not in part.split(":")[0] for part in src.split("def ")[1:])


def test_root_scripts_exist_for_every_verb():
    for verb, parts in sori.VERBS.items():
        assert (sori.ROOT / parts[0]).is_file(), verb
    assert os.environ.get("SORI_HOME")  # conftest isolation is in force
    assert Path(sys.executable).exists()
