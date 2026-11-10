import json
from pathlib import Path
import subprocess
import sys
import zipfile

import public_release
import start_sori
import preflight


def test_browser_package_needs_no_executable_builder(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "start_sori.py").write_text("pass\n")
    subprocess.run(["git", "add", "start_sori.py"], cwd=tmp_path, check=True)

    original_run = subprocess.run

    def refuse(args, **kwargs):
        if "PyInstaller" in args:
            raise AssertionError("The default browser package must not run an executable builder")
        return original_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", refuse)
    out = public_release.build(tmp_path)
    with zipfile.ZipFile(out / "Sori-browser.zip") as archive:
        assert archive.namelist() == ["Sori/start_sori.py"]
    assert not (out / "Sori-win64.zip").exists()
    assert "start_sori.py" in json.loads((out / "source-manifest.json").read_text())


def test_failed_setup_never_launches_app(monkeypatch, capsys):
    def fail(*args):
        raise preflight.NotReady("Setup is incomplete")

    monkeypatch.setattr(preflight, "ensure", fail)
    monkeypatch.setattr(subprocess, "call", lambda *a, **kw: sys.exit("unexpected launch"))
    assert start_sori.main([]) == 2
    assert "Setup is incomplete" in capsys.readouterr().err


def test_launcher_uses_prepared_interpreter_and_preserves_exit_status(monkeypatch):
    calls = []
    monkeypatch.setattr(preflight, "ensure", lambda verb: Path("prepared/python"))
    monkeypatch.setattr(subprocess, "call", lambda args: calls.append(args) or 7)
    assert start_sori.main(["--selftest"]) == 7
    assert calls[0][0] == str(Path("prepared/python"))
    assert calls[0][-1] == "--selftest"
    assert calls[0][1].endswith("app.py")
