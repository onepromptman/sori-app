"""A failed browser capture must never report or overwrite a stale image."""

import importlib.util
import base64
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def preview():
    path = Path(__file__).resolve().parents[1] / "tools" / "ui-preview" / "preview.py"
    spec = importlib.util.spec_from_file_location("sori_preview", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_failed_capture_preserves_previous_output(preview, tmp_path, monkeypatch):
    out = tmp_path / "existing.png"
    out.write_bytes(b"previous output")
    monkeypatch.setattr(preview.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1))
    assert not preview.capture(Path("edge"), "http://127.0.0.1/", out, "1400,860")
    assert out.read_bytes() == b"previous output"


def test_successful_capture_replaces_output(preview, tmp_path, monkeypatch):
    out = tmp_path / "existing.png"
    out.write_bytes(b"previous output")
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
    )

    def fake_run(args, **kwargs):
        shot = next(arg.removeprefix("--screenshot=") for arg in args if arg.startswith("--screenshot="))
        Path(shot).write_bytes(png)
        assert kwargs["timeout"] == 60
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(preview.subprocess, "run", fake_run)
    assert preview.capture(Path("edge"), "http://127.0.0.1/", out, "1400,860")
    assert out.read_bytes() == png
